"""Config loading and validation."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from solarmon.config import Config, load_config

REPO_ROOT = Path(__file__).parent.parent


def test_repo_config_loads_and_matches_proven():
    cfg = load_config(REPO_ROOT / "config.yaml")
    # Hardware identity per PROVEN.md
    assert cfg.stick.ip == "192.168.50.82"
    assert cfg.stick.serial == 3565365971
    assert cfg.stick.port == 8899
    assert cfg.stick.slave_id == 1
    # Alerts are off until a topic is set
    assert cfg.alerts.enabled is False


def test_polling_interval_floor():
    """Polling faster than 3s is refused: PROVEN.md says poll gently."""
    cfg = load_config(REPO_ROOT / "config.yaml")
    data = cfg.model_dump()
    data["polling"]["interval_s"] = 0.5
    with pytest.raises(ValidationError):
        Config.model_validate(data)


def test_bad_timezone_rejected():
    cfg = load_config(REPO_ROOT / "config.yaml")
    data = cfg.model_dump()
    data["tou"]["timezone"] = "Mars/OlympusMons"
    with pytest.raises(ValidationError):
        Config.model_validate(data)


def test_missing_file_message(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")
