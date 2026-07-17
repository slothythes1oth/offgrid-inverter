"""Configuration loading and validation.

One YAML file (config.yaml) validated by pydantic at startup. Fail fast with a
readable error rather than running on a half-broken config.
"""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field, field_validator


class StickConfig(BaseModel):
    ip: str
    serial: int = Field(gt=0)
    port: int = Field(default=8899, ge=1, le=65535)
    slave_id: int = Field(default=1, ge=0, le=247)
    socket_timeout_s: float = Field(default=8, gt=0)


class PollingConfig(BaseModel):
    interval_s: float = Field(default=5, ge=3, description="PROVEN.md: poll gently, ~5s")
    read_retries: int = Field(default=3, ge=1, le=5)
    backoff_s: float = Field(default=10, ge=1)
    stale_after_s: float = Field(default=30, ge=5)
    lockout_wait_s: float = Field(default=240, ge=60)


class BatteryConfig(BaseModel):
    nominal_kwh: float = Field(gt=0)
    usable_fraction: float = Field(default=0.8, gt=0, le=1)
    pack_count_expected: int = Field(default=3, ge=1)


class ThresholdsConfig(BaseModel):
    continuous_load_w: int = Field(default=6500, gt=0)
    low_soc_alert_pct: int = Field(default=40, ge=1, le=99)
    # Bypass relay limit per 120 V leg. Drives the twin-leg headroom lanes
    # (SPEC 8B.2) and the bypass threshold line on the load chart (SPEC 8A).
    bypass_amps_per_leg: int = Field(default=40, gt=0)


class LocationConfig(BaseModel):
    """Used ONLY by the offline sunrise/sunset math (SPEC 8B.3). Never sent
    anywhere; no network call ever depends on it."""

    lat: float = Field(default=45.04, ge=-90, le=90)
    lon: float = Field(default=-79.31, ge=-180, le=180)


class OutageConfig(BaseModel):
    debounce_polls: int = Field(default=3, ge=1)


class RuntimeEstimatorConfig(BaseModel):
    ema_window_min: float = Field(default=10, gt=0)


class TouRates(BaseModel):
    off_peak: float = Field(gt=0)
    mid_peak: float = Field(gt=0)
    on_peak: float = Field(gt=0)


class TouConfig(BaseModel):
    timezone: str = "America/Toronto"
    rates_cents_per_kwh: TouRates
    all_in_override_cents_per_kwh: float | None = None

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except Exception as e:
            raise ValueError(f"unknown IANA timezone: {v!r}") from e
        return v


class AlertsConfig(BaseModel):
    ntfy_topic: str = ""
    ntfy_server: str = "https://ntfy.sh"

    @property
    def enabled(self) -> bool:
        return bool(self.ntfy_topic.strip())


class DatabaseConfig(BaseModel):
    path: str = "data/solarmon.db"
    retention_days_raw: int = Field(default=30, ge=1)


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "data/collector.log"

    @field_validator("level")
    @classmethod
    def _valid_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR"}
        if v.upper() not in allowed:
            raise ValueError(f"logging.level must be one of {sorted(allowed)}")
        return v.upper()


class Config(BaseModel):
    stick: StickConfig
    polling: PollingConfig = PollingConfig()
    battery: BatteryConfig
    thresholds: ThresholdsConfig = ThresholdsConfig()
    location: LocationConfig = LocationConfig()
    outage: OutageConfig = OutageConfig()
    runtime_estimator: RuntimeEstimatorConfig = RuntimeEstimatorConfig()
    tou: TouConfig
    alerts: AlertsConfig = AlertsConfig()
    database: DatabaseConfig = DatabaseConfig()
    logging: LoggingConfig = LoggingConfig()


def load_config(path: str | Path = "config.yaml") -> Config:
    """Load and validate the config file. Raises with a clear message on any problem."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p.resolve()}")
    with p.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"Config file {p} is empty or not a YAML mapping")
    return Config.model_validate(raw)
