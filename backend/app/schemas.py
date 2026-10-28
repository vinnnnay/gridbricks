"""Pydantic response models for the wind forecast API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    rows: dict[str, int]


class ConfigResponse(BaseModel):
    start_date: str
    end_date: str
    default_cutoff_hour: int
    default_cutoff_minute: int
    timezone: str
    actual_coverage: dict[str, str | None]
    forecast_coverage: dict[str, str | None]
    last_publish_time: str | None


class ForecastVsActualRow(BaseModel):
    startTime: str
    forecast: float
    actual: float
    publishTime: str
    horizon_h: float
    error: float


class MetricsResponse(BaseModel):
    n: int
    mae: float | None
    rmse: float | None
    bias: float | None
    mape: float | None
    p50: float | None
    p90: float | None
    p95: float | None
    p99: float | None
    over_forecast_share: float | None
    under_forecast_share: float | None
    dropped_rows: dict[str, int]


class HorizonRow(BaseModel):
    horizon: str
    mae: float
    rmse: float
    bias: float
    n: int


class HourRow(BaseModel):
    hour: int
    mae: float
    bias: float
    n: int


class ActualLevelRow(BaseModel):
    actual_level: str
    mae: float
    bias: float
    n: int


class HistogramRow(BaseModel):
    bin_start: float
    bin_end: float
    count: int


class LatestForecastRow(BaseModel):
    startTime: str
    forecast: float
    publishTime: str
    horizon_h: float
    p10: float | None
    p90: float | None
    calibration_n: int
    calibration_source: str
    actual: float | None


class LatestForecastResponse(BaseModel):
    delivery_date: str
    cutoff: str
    publishTime: str
    rows: list[LatestForecastRow]
    count: int
    coverage: dict[str, int | float | None]


class CutoffSensitivityRow(BaseModel):
    cutoff_hour: int
    cutoff: str
    mae: float | None
    n: int


class RevisionPoint(BaseModel):
    startTime: str
    forecast: float


class ForecastRevision(BaseModel):
    publishTime: str
    rows: list[RevisionPoint]


class RevisionTrackerResponse(BaseModel):
    delivery_date: str
    actuals: list[dict[str, str | float]]
    revisions: list[ForecastRevision]
    revision_count: int


class NaiveBaselineResponse(BaseModel):
    n: int
    mae_forecast: float | None
    mae_baseline: float | None
    skill_score: float | None


class BiasCorrectionResponse(BaseModel):
    n: int
    mae_forecast: float | None
    mae_corrected: float | None
    mae_improvement: float | None
    mae_improvement_share: float | None


class WindRegimeRow(BaseModel):
    regime: str
    actual_min: float
    actual_max: float
    mae: float
    bias: float
    n: int


class DayHourErrorRow(BaseModel):
    delivery_date: str
    hour: int
    mae: float
    bias: float
    n: int


class RampEventRow(BaseModel):
    startTime: str
    actual: float
    forecast: float
    previous_actual: float
    previous_forecast: float | None
    forecast_interval_minutes: float | None
    actual_ramp: float
    forecast_ramp: float | None
    forecast_error: float
    direction_caught: bool


class RampEventsResponse(BaseModel):
    summary: dict[str, int | float | None]
    events: list[RampEventRow]
