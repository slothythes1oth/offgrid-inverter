"""ntfy alerts: config-gated, deduped, with priorities per SPEC section 6.

Gate: alerts.ntfy_topic empty -> nothing is ever sent; every would-be alert
is logged as [dry-run] instead. Dedupe: a condition key alerts once when it
becomes active and cannot re-alert until cleared (a collector restart
mid-outage re-marks the key active WITHOUT sending, via mark_active).

Known v1 limit (README): if this laptop is asleep, no alerts.
"""

from __future__ import annotations

import logging

import requests

from solarmon.config import AlertsConfig

log = logging.getLogger("alerts")

# ntfy priorities: 5 urgent (outage raised / fault raised / low SoC), 3 default
PRIORITY_CRITICAL = 5
PRIORITY_DEFAULT = 3

_SEND_TIMEOUT_S = 5


class AlertManager:
    def __init__(self, cfg: AlertsConfig, session: requests.Session | None = None):
        self.cfg = cfg
        self._session = session or requests.Session()
        self._active: set[str] = set()
        self.sent_count = 0

    # -- dedupe state --------------------------------------------------------

    def mark_active(self, key: str) -> None:
        """Mark a condition active without alerting (restart into an ongoing
        condition must not re-alert)."""
        self._active.add(key)

    def clear(self, key: str) -> None:
        self._active.discard(key)

    # -- sending -------------------------------------------------------------

    def alert_once(self, key: str, title: str, message: str, priority: int) -> bool:
        """Alert for a condition becoming active. No-op if already active.
        Returns True if the alert was sent (or dry-run logged)."""
        if key in self._active:
            return False
        self._active.add(key)
        self._send(title, message, priority)
        return True

    def alert_edge(self, title: str, message: str, priority: int = PRIORITY_DEFAULT) -> None:
        """Alert for a one-off edge (grid restored, fault cleared). Edge
        detection upstream is the dedupe."""
        self._send(title, message, priority)

    def _send(self, title: str, message: str, priority: int) -> None:
        if not self.cfg.enabled:
            log.info("[dry-run] ntfy p%d | %s | %s", priority, title, message)
            return
        try:
            resp = self._session.post(
                f"{self.cfg.ntfy_server.rstrip('/')}/{self.cfg.ntfy_topic}",
                data=message.encode("utf-8"),
                headers={"Title": title, "Priority": str(priority)},
                timeout=_SEND_TIMEOUT_S,
            )
            resp.raise_for_status()
            self.sent_count += 1
            log.info("ntfy sent p%d | %s", priority, title)
        except Exception as e:
            # An alert failure must never break polling.
            log.error("ntfy send failed: %s", e)


def fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    m, _ = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"
