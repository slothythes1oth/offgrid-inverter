"""Alert manager: gating, dedupe, priorities, message content."""

from solarmon.alerts import PRIORITY_CRITICAL, AlertManager, fmt_duration
from solarmon.config import AlertsConfig


class FakeSession:
    def __init__(self):
        self.posts = []

    def post(self, url, data=None, headers=None, timeout=None):
        self.posts.append({"url": url, "data": data, "headers": headers})

        class R:
            def raise_for_status(self):
                pass

        return R()


def mgr(topic="test-topic"):
    session = FakeSession()
    m = AlertManager(AlertsConfig(ntfy_topic=topic), session=session)
    return m, session


def test_disabled_sends_nothing():
    m, session = mgr(topic="")
    m.alert_once("outage", "Grid lost", "SoC 96%", PRIORITY_CRITICAL)
    assert session.posts == []  # dry-run: logged, never posted


def test_dedupe_same_condition():
    m, session = mgr()
    assert m.alert_once("outage", "Grid lost", "x", PRIORITY_CRITICAL) is True
    assert m.alert_once("outage", "Grid lost", "x", PRIORITY_CRITICAL) is False
    assert len(session.posts) == 1


def test_clear_allows_next_activation():
    m, session = mgr()
    m.alert_once("outage", "Grid lost", "x", PRIORITY_CRITICAL)
    m.clear("outage")
    assert m.alert_once("outage", "Grid lost", "x", PRIORITY_CRITICAL) is True
    assert len(session.posts) == 2


def test_mark_active_suppresses_without_sending():
    """Collector restart mid-outage: condition marked active, no alert."""
    m, session = mgr()
    m.mark_active("outage")
    assert m.alert_once("outage", "Grid lost", "x", PRIORITY_CRITICAL) is False
    assert session.posts == []


def test_priority_and_topic_on_wire():
    m, session = mgr(topic="my-solar")
    m.alert_once("fault", "Inverter fault: 13 (bypass overload)", "Load 5000 W", 5)
    p = session.posts[0]
    assert p["url"].endswith("/my-solar")
    assert p["headers"]["Priority"] == "5"
    assert "bypass overload" in p["headers"]["Title"]


def test_send_failure_never_raises():
    class BoomSession:
        def post(self, *a, **k):
            raise OSError("network down")

    m = AlertManager(AlertsConfig(ntfy_topic="t"), session=BoomSession())
    m.alert_once("outage", "Grid lost", "x", 5)  # must not raise


def test_fmt_duration():
    assert fmt_duration(15) == "15s"
    assert fmt_duration(90) == "1m"
    assert fmt_duration(6003) == "1h 40m"
