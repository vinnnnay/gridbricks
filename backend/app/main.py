"""FastAPI routes for preprocessed day-ahead wind forecast analysis."""
from __future__ import annotations

import math
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .analysis import (
    compute_metrics,
    analyze_ramp_events,
    compare_naive_baseline,
    error_by_day_hour,
    error_by_actual_level,
    error_by_horizon,
    error_by_hour,
    error_by_wind_regime,
    error_histogram,
    forecast_uncertainty,
    join_actuals,
    select_decision_forecast,
    walk_forward_bias_correction,
)
from .schemas import (
    ActualLevelRow,
    BiasCorrectionResponse,
    ConfigResponse,
    CutoffSensitivityRow,
    DayHourErrorRow,
    ForecastRevision,
    ForecastVsActualRow,
    HealthResponse,
    HourRow,
    HorizonRow,
    HistogramRow,
    LatestForecastResponse,
    MetricsResponse,
    NaiveBaselineResponse,
    RampEventsResponse,
    RevisionTrackerResponse,
    WindRegimeRow,
)

DATA_START = date(2026, 1, 2)
DATA_END = date(2026, 2, 1)
LONDON_TZ = "Europe/London"
PROCESSED_DIR = Path(
    os.environ.get(
        "PROCESSED_DIR", Path(__file__).resolve().parents[1] / "data" / "processed"
    )
)


def _read_processed() -> tuple[pd.DataFrame, pd.DataFrame]:
    actual_path = PROCESSED_DIR / "wind_actuals.csv"
    forecast_path = PROCESSED_DIR / "wind_forecasts.csv"
    missing = [path.name for path in (actual_path, forecast_path) if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"Processed data file(s) missing from {PROCESSED_DIR}: {', '.join(missing)}"
        )
    actuals = pd.read_csv(actual_path, parse_dates=["startTime"])
    forecasts = pd.read_csv(forecast_path, parse_dates=["startTime", "publishTime"])
    actuals["startTime"] = pd.to_datetime(actuals["startTime"], utc=True)
    forecasts["startTime"] = pd.to_datetime(forecasts["startTime"], utc=True)
    forecasts["publishTime"] = pd.to_datetime(forecasts["publishTime"], utc=True)
    return actuals, forecasts


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load immutable processed datasets once when the API starts."""
    app.state.actuals, app.state.forecasts = _read_processed()
    yield


app = FastAPI(
    title="Wind Forecast Monitoring API",
    description="Historical GB wind forecast analysis using preprocessed Elexon data.",
    lifespan=lifespan,
)

origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials="*" not in origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _data(request: Request) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        return request.app.state.actuals, request.app.state.forecasts
    except AttributeError as exc:
        raise HTTPException(status_code=503, detail="Processed data is not loaded") from exc


def _validate_date_range(start: date, end: date) -> None:
    if start < DATA_START or end > DATA_END:
        raise HTTPException(
            status_code=422,
            detail=f"Dates must be within {DATA_START.isoformat()} and {DATA_END.isoformat()}",
        )
    if start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")


def _validate_cutoff(cutoff_hour: int, cutoff_minute: int) -> None:
    if not 0 <= cutoff_hour <= 23:
        raise HTTPException(status_code=422, detail="cutoff_hour must be between 0 and 23")
    if not 0 <= cutoff_minute <= 59:
        raise HTTPException(status_code=422, detail="cutoff_minute must be between 0 and 59")


def _local_dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True).dt.tz_convert(LONDON_TZ).dt.date


def _filter_range(
    forecasts: pd.DataFrame, actuals: pd.DataFrame, start: date, end: date
) -> tuple[pd.DataFrame, pd.DataFrame]:
    forecast_mask = _local_dates(forecasts["startTime"]).between(start, end)
    actual_mask = _local_dates(actuals["startTime"]).between(start, end)
    return forecasts.loc[forecast_mask].copy(), actuals.loc[actual_mask].copy()


def _decision_data(
    forecasts: pd.DataFrame,
    actuals: pd.DataFrame,
    cutoff_hour: int,
    cutoff_minute: int,
) -> tuple[pd.DataFrame, dict[str, int]]:
    decision = select_decision_forecast(forecasts, cutoff_hour, cutoff_minute)
    joined, counts = join_actuals(decision, actuals)
    forecast_times = pd.Index(pd.to_datetime(forecasts["startTime"], utc=True).unique())
    decision_times = pd.Index(pd.to_datetime(decision["startTime"], utc=True).unique())
    counts["targets_without_eligible_forecast"] = int(
        len(forecast_times.difference(decision_times))
    )
    counts["matched_rows_dropped_invalid_values"] = int(
        counts["matched"] - len(joined)
    )
    return joined, counts


def _json_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)) and not math.isfinite(value):
        return None
    if isinstance(value, pd.Timestamp):
        stamp = value
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        else:
            stamp = stamp.tz_convert("UTC")
        return stamp.isoformat().replace("+00:00", "Z")
    if isinstance(value, datetime):
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        return stamp.tz_convert("UTC").isoformat().replace("+00:00", "Z")
    if hasattr(value, "item"):
        return _json_value(value.item())
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {key: _json_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _common_params(
    cutoff_hour: int, cutoff_minute: int, start: date, end: date
) -> tuple[date, date]:
    _validate_cutoff(cutoff_hour, cutoff_minute)
    _validate_date_range(start, end)
    return start, end


@app.get("/api/health", response_model=HealthResponse)
def health(request: Request) -> dict[str, Any]:
    actuals, forecasts = _data(request)
    return {"status": "ok", "rows": {"actuals": len(actuals), "forecasts": len(forecasts)}}


@app.get("/api/config", response_model=ConfigResponse)
def config(request: Request) -> dict[str, Any]:
    actuals, forecasts = _data(request)
    actual_times = pd.to_datetime(actuals["startTime"], utc=True)
    forecast_times = pd.to_datetime(forecasts["startTime"], utc=True)
    publish_times = pd.to_datetime(forecasts["publishTime"], utc=True)
    return {
        "start_date": DATA_START.isoformat(),
        "end_date": DATA_END.isoformat(),
        "default_cutoff_hour": 9,
        "default_cutoff_minute": 0,
        "timezone": LONDON_TZ,
        "actual_coverage": {
            "start": _json_value(actual_times.min()) if not actual_times.empty else None,
            "end": _json_value(actual_times.max()) if not actual_times.empty else None,
        },
        "forecast_coverage": {
            "start": _json_value(forecast_times.min()) if not forecast_times.empty else None,
            "end": _json_value(forecast_times.max()) if not forecast_times.empty else None,
        },
        "last_publish_time": _json_value(publish_times.max()) if not publish_times.empty else None,
    }


@app.get("/api/forecast-vs-actual", response_model=list[ForecastVsActualRow])
def forecast_vs_actual(
    request: Request,
    cutoff_hour: int = Query(9, ge=0, le=23),
    cutoff_minute: int = Query(0, ge=0, le=59),
    start: date = Query(DATA_START),
    end: date = Query(DATA_END),
) -> list[dict[str, Any]]:
    _common_params(cutoff_hour, cutoff_minute, start, end)
    actuals, forecasts = _data(request)
    forecasts, actuals = _filter_range(forecasts, actuals, start, end)
    joined, _ = _decision_data(forecasts, actuals, cutoff_hour, cutoff_minute)
    if joined.empty:
        return []
    rows = joined[
        ["startTime", "generation", "actual", "publishTime", "horizon_h", "error"]
    ].rename(columns={"generation": "forecast"})
    return _records(rows)


@app.get("/api/metrics", response_model=MetricsResponse)
def metrics(
    request: Request,
    cutoff_hour: int = Query(9, ge=0, le=23),
    cutoff_minute: int = Query(0, ge=0, le=59),
    start: date = Query(DATA_START),
    end: date = Query(DATA_END),
) -> dict[str, Any]:
    _common_params(cutoff_hour, cutoff_minute, start, end)
    actuals, forecasts = _data(request)
    forecasts, actuals = _filter_range(forecasts, actuals, start, end)
    joined, dropped = _decision_data(forecasts, actuals, cutoff_hour, cutoff_minute)
    return {**compute_metrics(joined), "dropped_rows": dropped}


@app.get("/api/error-by-horizon", response_model=list[HorizonRow])
def api_error_by_horizon(
    request: Request,
    cutoff_hour: int = Query(9, ge=0, le=23),
    cutoff_minute: int = Query(0, ge=0, le=59),
    start: date = Query(DATA_START),
    end: date = Query(DATA_END),
) -> list[dict[str, Any]]:
    _common_params(cutoff_hour, cutoff_minute, start, end)
    actuals, forecasts = _data(request)
    forecasts, actuals = _filter_range(forecasts, actuals, start, end)
    return _records(error_by_horizon(forecasts, actuals))


@app.get("/api/error-by-hour", response_model=list[HourRow])
def api_error_by_hour(
    request: Request,
    cutoff_hour: int = Query(9, ge=0, le=23),
    cutoff_minute: int = Query(0, ge=0, le=59),
    start: date = Query(DATA_START),
    end: date = Query(DATA_END),
) -> list[dict[str, Any]]:
    _common_params(cutoff_hour, cutoff_minute, start, end)
    actuals, forecasts = _data(request)
    forecasts, actuals = _filter_range(forecasts, actuals, start, end)
    joined, _ = _decision_data(forecasts, actuals, cutoff_hour, cutoff_minute)
    return _records(error_by_hour(joined))


@app.get("/api/error-by-level", response_model=list[ActualLevelRow])
def api_error_by_level(
    request: Request,
    cutoff_hour: int = Query(9, ge=0, le=23),
    cutoff_minute: int = Query(0, ge=0, le=59),
    start: date = Query(DATA_START),
    end: date = Query(DATA_END),
) -> list[dict[str, Any]]:
    _common_params(cutoff_hour, cutoff_minute, start, end)
    actuals, forecasts = _data(request)
    forecasts, actuals = _filter_range(forecasts, actuals, start, end)
    joined, _ = _decision_data(forecasts, actuals, cutoff_hour, cutoff_minute)
    return _records(error_by_actual_level(joined))


@app.get("/api/error-histogram", response_model=list[HistogramRow])
def api_error_histogram(
    request: Request,
    cutoff_hour: int = Query(9, ge=0, le=23),
    cutoff_minute: int = Query(0, ge=0, le=59),
    start: date = Query(DATA_START),
    end: date = Query(DATA_END),
) -> list[dict[str, int | float]]:
    _common_params(cutoff_hour, cutoff_minute, start, end)
    actuals, forecasts = _data(request)
    forecasts, actuals = _filter_range(forecasts, actuals, start, end)
    joined, _ = _decision_data(forecasts, actuals, cutoff_hour, cutoff_minute)
    return error_histogram(joined)


@app.get("/api/latest-forecast", response_model=LatestForecastResponse)
def latest_forecast(
    request: Request,
    delivery_date: date,
    cutoff_hour: int = Query(9, ge=0, le=23),
    cutoff_minute: int = Query(0, ge=0, le=59),
) -> dict[str, Any]:
    _validate_cutoff(cutoff_hour, cutoff_minute)
    _validate_date_range(delivery_date, delivery_date)
    actuals, all_forecasts = _data(request)
    target_forecasts = all_forecasts.loc[
        _local_dates(all_forecasts["startTime"]) == delivery_date
    ].copy()
    if target_forecasts.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No forecasts are available for {delivery_date.isoformat()}",
        )
    eligible = select_decision_forecast(
        target_forecasts, cutoff_hour, cutoff_minute
    )
    if eligible.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No forecast was published by the cutoff for {delivery_date.isoformat()}",
        )
    bands, coverage = forecast_uncertainty(
        all_forecasts,
        actuals,
        delivery_date,
        cutoff_hour,
        cutoff_minute,
    )
    if bands.empty:
        bands = eligible.copy()
        bands["p10"] = pd.NA
        bands["p90"] = pd.NA
        bands["calibration_n"] = 0
        bands["calibration_source"] = "unavailable"
    publish_time = pd.to_datetime(bands["publishTime"], utc=True).max()
    bands = bands.loc[pd.to_datetime(bands["publishTime"], utc=True) == publish_time]
    cutoff = pd.Timestamp(eligible["cutoff"].iloc[0])
    forecast_column = "forecast" if "forecast" in bands.columns else "generation"
    output = bands.rename(columns={forecast_column: "forecast"})
    output["p10"] = pd.to_numeric(output["p10"], errors="coerce")
    output["p90"] = pd.to_numeric(output["p90"], errors="coerce")
    return {
        "delivery_date": delivery_date.isoformat(),
        "cutoff": _json_value(cutoff),
        "publishTime": _json_value(publish_time),
        "rows": _records(
            output[
                [
                    "startTime",
                    "forecast",
                    "publishTime",
                    "horizon_h",
                    "p10",
                    "p90",
                    "calibration_n",
                    "calibration_source",
                    "actual",
                ]
            ]
        ),
        "count": len(output),
        "coverage": coverage,
    }


@app.get("/api/cutoff-sensitivity", response_model=list[CutoffSensitivityRow])
def cutoff_sensitivity(
    request: Request,
    cutoff_minute: int = Query(0, ge=0, le=59),
    start: date = Query(DATA_START),
    end: date = Query(DATA_END),
) -> list[dict[str, Any]]:
    _validate_cutoff(6, cutoff_minute)
    _validate_date_range(start, end)
    actuals, forecasts = _data(request)
    forecasts, actuals = _filter_range(forecasts, actuals, start, end)
    rows = []
    for hour in range(6, 13):
        decision = select_decision_forecast(forecasts, hour, cutoff_minute)
        joined, _ = join_actuals(decision, actuals)
        metric = compute_metrics(joined)
        rows.append(
            {
                "cutoff_hour": hour,
                "cutoff": f"{hour:02d}:{cutoff_minute:02d}",
                "mae": metric["mae"],
                "n": metric["n"],
            }
        )
    return rows


@app.get("/api/forecast-revisions", response_model=RevisionTrackerResponse)
def forecast_revisions(
    request: Request,
    delivery_date: date,
) -> dict[str, Any]:
    _validate_date_range(delivery_date, delivery_date)
    actuals, forecasts = _data(request)
    day_forecasts = forecasts.loc[
        _local_dates(forecasts["startTime"]) == delivery_date
    ].copy()
    if day_forecasts.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No forecast revisions are available for {delivery_date.isoformat()}",
        )
    forecast_column = "forecast" if "forecast" in day_forecasts.columns else "generation"
    actual_rows = actuals.loc[
        _local_dates(actuals["startTime"]) == delivery_date, ["startTime", "actual"]
    ].sort_values("startTime")
    day_forecasts[forecast_column] = pd.to_numeric(
        day_forecasts[forecast_column], errors="coerce"
    )
    day_forecasts = day_forecasts.dropna(subset=[forecast_column])
    revisions = []
    for publish_time, group in day_forecasts.groupby("publishTime", sort=True):
        rows = group.sort_values("startTime")[["startTime", forecast_column]].rename(
            columns={forecast_column: "forecast"}
        )
        revisions.append(
            {"publishTime": _json_value(pd.Timestamp(publish_time)), "rows": _records(rows)}
        )
    return {
        "delivery_date": delivery_date.isoformat(),
        "actuals": _records(actual_rows),
        "revisions": revisions,
        "revision_count": len(revisions),
    }


@app.get("/api/naive-baseline", response_model=NaiveBaselineResponse)
def naive_baseline(
    request: Request,
    cutoff_hour: int = Query(9, ge=0, le=23),
    cutoff_minute: int = Query(0, ge=0, le=59),
    start: date = Query(DATA_START),
    end: date = Query(DATA_END),
) -> dict[str, Any]:
    _common_params(cutoff_hour, cutoff_minute, start, end)
    actuals, all_forecasts = _data(request)
    forecasts, selected_actuals = _filter_range(all_forecasts, actuals, start, end)
    decisions = select_decision_forecast(forecasts, cutoff_hour, cutoff_minute)
    joined, _ = join_actuals(decisions, selected_actuals)
    return compare_naive_baseline(joined, actuals)


@app.get("/api/bias-correction", response_model=BiasCorrectionResponse)
def bias_correction(
    request: Request,
    cutoff_hour: int = Query(9, ge=0, le=23),
    cutoff_minute: int = Query(0, ge=0, le=59),
    start: date = Query(DATA_START),
    end: date = Query(DATA_END),
) -> dict[str, Any]:
    _common_params(cutoff_hour, cutoff_minute, start, end)
    actuals, forecasts = _data(request)
    all_decisions = select_decision_forecast(forecasts, cutoff_hour, cutoff_minute)
    all_joined, _ = join_actuals(all_decisions, actuals)
    corrected, _ = walk_forward_bias_correction(all_joined)
    dates = _local_dates(corrected["startTime"])
    selected = corrected.loc[dates.between(start, end)].dropna(
        subset=["actual", "generation", "corrected_forecast"]
    )
    if selected.empty:
        return {
            "n": 0,
            "mae_forecast": None,
            "mae_corrected": None,
            "mae_improvement": None,
            "mae_improvement_share": None,
        }
    raw_mae = float((selected["generation"] - selected["actual"]).abs().mean())
    corrected_mae = float(
        (selected["corrected_forecast"] - selected["actual"]).abs().mean()
    )
    return {
        "n": int(len(selected)),
        "mae_forecast": raw_mae,
        "mae_corrected": corrected_mae,
        "mae_improvement": raw_mae - corrected_mae,
        "mae_improvement_share": (
            float((raw_mae - corrected_mae) / raw_mae) if raw_mae else None
        ),
    }


@app.get("/api/ramp-events", response_model=RampEventsResponse)
def ramp_events(
    request: Request,
    cutoff_hour: int = Query(9, ge=0, le=23),
    cutoff_minute: int = Query(0, ge=0, le=59),
    start: date = Query(DATA_START),
    end: date = Query(DATA_END),
    threshold_mw: float = Query(500.0, gt=0),
) -> dict[str, Any]:
    _common_params(cutoff_hour, cutoff_minute, start, end)
    actuals, forecasts = _data(request)
    decisions = select_decision_forecast(forecasts, cutoff_hour, cutoff_minute)
    events, _ = analyze_ramp_events(decisions, actuals, threshold_mw=threshold_mw)
    event_dates = _local_dates(events["startTime"])
    events = events.loc[event_dates.between(start, end)].copy()
    available = events.dropna(subset=["forecast_ramp"])
    caught = int(available["direction_caught"].sum())
    summary = {
        "threshold_mw": float(threshold_mw),
        "event_count": int(len(events)),
        "forecast_direction_available": int(len(available)),
        "direction_caught": caught,
        "direction_caught_share": float(caught / len(available)) if len(available) else None,
        "mae_on_ramps": (
            float(events["forecast_error"].abs().mean()) if not events.empty else None
        ),
    }
    return {"summary": summary, "events": _records(events)}


@app.get("/api/error-by-regime", response_model=list[WindRegimeRow])
def api_error_by_regime(
    request: Request,
    cutoff_hour: int = Query(9, ge=0, le=23),
    cutoff_minute: int = Query(0, ge=0, le=59),
    start: date = Query(DATA_START),
    end: date = Query(DATA_END),
) -> list[dict[str, Any]]:
    _common_params(cutoff_hour, cutoff_minute, start, end)
    actuals, forecasts = _data(request)
    forecasts, actuals = _filter_range(forecasts, actuals, start, end)
    joined, _ = _decision_data(forecasts, actuals, cutoff_hour, cutoff_minute)
    return _records(error_by_wind_regime(joined))


@app.get("/api/error-heatmap", response_model=list[DayHourErrorRow])
def api_error_heatmap(
    request: Request,
    cutoff_hour: int = Query(9, ge=0, le=23),
    cutoff_minute: int = Query(0, ge=0, le=59),
    start: date = Query(DATA_START),
    end: date = Query(DATA_END),
) -> list[dict[str, Any]]:
    _common_params(cutoff_hour, cutoff_minute, start, end)
    actuals, forecasts = _data(request)
    forecasts, actuals = _filter_range(forecasts, actuals, start, end)
    joined, _ = _decision_data(forecasts, actuals, cutoff_hour, cutoff_minute)
    return _records(error_by_day_hour(joined))
