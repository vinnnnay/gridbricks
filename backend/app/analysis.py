"""Pure analysis functions for day-ahead wind forecast accuracy."""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, time, timedelta
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

LONDON_TZ = "Europe/London"


def _validate_cutoff(cutoff_hour: int, cutoff_minute: int) -> None:
    if not 0 <= cutoff_hour <= 23:
        raise ValueError("cutoff_hour must be between 0 and 23")
    if not 0 <= cutoff_minute <= 59:
        raise ValueError("cutoff_minute must be between 0 and 59")


def _require_columns(df: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{name} is missing required columns: {', '.join(missing)}")


def _forecast_column(df: pd.DataFrame, name: str) -> str:
    if "forecast" in df.columns:
        return "forecast"
    if "generation" in df.columns:
        return "generation"
    raise ValueError(f"{name} is missing required column: forecast")


def add_cutoff(
    forecasts: pd.DataFrame,
    cutoff_hour: int = 9,
    cutoff_minute: int = 0,
) -> pd.DataFrame:
    """Add the local D-1 cutoff in UTC and forecast horizon in hours."""
    _validate_cutoff(cutoff_hour, cutoff_minute)
    _require_columns(forecasts, ["startTime", "publishTime"], "forecasts")
    result = forecasts.copy()
    result["startTime"] = pd.to_datetime(result["startTime"], utc=True)
    result["publishTime"] = pd.to_datetime(result["publishTime"], utc=True)

    if result.empty:
        result["cutoff"] = pd.Series(dtype="datetime64[ns, UTC]")
        result["horizon_h"] = pd.Series(dtype="float64")
        return result

    target_dates = result["startTime"].dt.tz_convert(LONDON_TZ).dt.date
    local_cutoffs = pd.DatetimeIndex(
        [
            datetime.combine(
                target_date - timedelta(days=1), time(cutoff_hour, cutoff_minute)
            )
            for target_date in target_dates
        ]
    ).tz_localize(LONDON_TZ, ambiguous="raise", nonexistent="raise")
    result["cutoff"] = local_cutoffs.tz_convert("UTC")
    result["horizon_h"] = (
        (result["startTime"] - result["publishTime"]).dt.total_seconds() / 3600
    )
    return result


def select_decision_forecast(
    forecasts: pd.DataFrame,
    cutoff_hour: int = 9,
    cutoff_minute: int = 0,
) -> pd.DataFrame:
    """Keep the latest eligible forecast per target, dropping targets without one."""
    prepared = add_cutoff(forecasts, cutoff_hour, cutoff_minute)
    eligible = prepared.loc[prepared["publishTime"] <= prepared["cutoff"]].copy()
    target_count = prepared["startTime"].nunique()
    eligible_count = eligible["startTime"].nunique()
    dropped_count = target_count - eligible_count
    if dropped_count:
        log.warning(
            "Dropped %d target(s) without a forecast published by the decision cutoff",
            dropped_count,
        )
    if eligible.empty:
        return eligible
    return (
        eligible.sort_values(["startTime", "publishTime"])
        .drop_duplicates("startTime", keep="last")
        .reset_index(drop=True)
    )


def _level_edges(values: pd.Series, bins: int) -> np.ndarray:
    unique_count = int(values.nunique())
    if unique_count <= 1:
        return np.array([-np.inf, np.inf])
    _, edges = pd.qcut(
        values.astype(float), q=min(bins, unique_count), retbins=True, duplicates="drop"
    )
    return np.concatenate(([-np.inf], edges[1:-1], [np.inf]))


def _assign_band_groups(
    frame: pd.DataFrame, level_edges: np.ndarray, bin_hours: int
) -> pd.DataFrame:
    result = frame.copy()
    result["horizon_bin"] = np.floor(result["horizon_h"] / bin_hours).astype(int)
    result["level_bin"] = pd.cut(
        result["generation"].astype(float),
        bins=level_edges,
        labels=False,
        include_lowest=True,
    )
    return result


def _predict_residual_bands(
    training: pd.DataFrame,
    targets: pd.DataFrame,
    bin_hours: int,
    level_bins: int,
    min_samples: int,
) -> pd.DataFrame:
    result = targets.copy()
    result["p10"] = np.nan
    result["p90"] = np.nan
    result["calibration_n"] = 0
    result["calibration_source"] = "unavailable"
    if training.empty or targets.empty:
        return result

    level_edges = _level_edges(training["generation"], level_bins)
    training = _assign_band_groups(training, level_edges, bin_hours)
    result = _assign_band_groups(result, level_edges, bin_hours)
    grouped = {
        key: group["residual"].to_numpy(dtype=float)
        for key, group in training.groupby(["horizon_bin", "level_bin"], observed=True)
    }
    horizon_groups = {
        key: group["residual"].to_numpy(dtype=float)
        for key, group in training.groupby("horizon_bin", observed=True)
    }
    all_residuals = training["residual"].to_numpy(dtype=float)

    for index, row in result.iterrows():
        residuals = grouped.get((row["horizon_bin"], row["level_bin"]))
        source = "horizon and wind level"
        if residuals is None or len(residuals) < min_samples:
            residuals = horizon_groups.get(row["horizon_bin"])
            source = "horizon"
        if residuals is None or len(residuals) < min_samples:
            residuals = all_residuals
            source = "all horizons and wind levels"
        if not len(residuals):
            continue
        result.at[index, "p10"] = max(
            0.0, float(row["generation"] + np.quantile(residuals, 0.10))
        )
        result.at[index, "p90"] = max(
            result.at[index, "p10"],
            float(row["generation"] + np.quantile(residuals, 0.90)),
        )
        result.at[index, "calibration_n"] = int(len(residuals))
        result.at[index, "calibration_source"] = source

    return result.drop(columns=["horizon_bin", "level_bin"])


def forecast_uncertainty(
    forecasts: pd.DataFrame,
    actuals: pd.DataFrame,
    delivery_date: date,
    cutoff_hour: int = 9,
    cutoff_minute: int = 0,
    bin_hours: int = 6,
    level_bins: int = 5,
    min_samples: int = 20,
) -> tuple[pd.DataFrame, dict[str, int | float | None]]:
    """Build conditional P10-P90 actual-wind bands and leave-one-day-out coverage.

    Residuals are actual minus forecast. Calibration uses other delivery days,
    and coverage is tested by holding out each calibration delivery day.
    """
    if bin_hours <= 0 or level_bins < 1 or min_samples < 1:
        raise ValueError("bin_hours, level_bins, and min_samples must be positive")
    decisions = select_decision_forecast(forecasts, cutoff_hour, cutoff_minute)
    if "forecast" in decisions.columns:
        decisions = decisions.rename(columns={"forecast": "generation"})
    decisions["generation"] = pd.to_numeric(decisions["generation"], errors="coerce")
    history, _ = join_actuals(decisions, actuals)
    if not decisions.empty:
        target_mask = (
            pd.to_datetime(decisions["startTime"], utc=True)
            .dt.tz_convert(LONDON_TZ)
            .dt.date
            == delivery_date
        )
        target_rows = decisions.loc[target_mask].copy()
        actual_rows = actuals[["startTime", "actual"]].copy()
        actual_rows["startTime"] = pd.to_datetime(actual_rows["startTime"], utc=True)
        target_rows = target_rows.merge(actual_rows, on="startTime", how="left")
    else:
        target_rows = decisions.copy()
        target_rows["actual"] = pd.Series(dtype="float64")
    history["residual"] = history["actual"] - history["generation"]
    history["delivery_date"] = (
        pd.to_datetime(history["startTime"], utc=True)
        .dt.tz_convert(LONDON_TZ)
        .dt.date
    )
    if decisions.empty:
        return pd.DataFrame(
            columns=[
                "startTime",
                "publishTime",
                "generation",
                "horizon_h",
                "p10",
                "p90",
                "calibration_n",
                "calibration_source",
            ]
        ), {"covered": 0, "total": 0, "coverage": None}
    calibration = history.loc[history["delivery_date"] != delivery_date].copy()
    bands = _predict_residual_bands(
        calibration, target_rows, bin_hours, level_bins, min_samples
    )
    cross_validated: list[pd.DataFrame] = []
    for held_out_date in calibration["delivery_date"].unique():
        held_out = calibration.loc[calibration["delivery_date"] == held_out_date]
        training = calibration.loc[calibration["delivery_date"] != held_out_date]
        validation = _predict_residual_bands(
            training, held_out, bin_hours, level_bins, min_samples
        )
        cross_validated.append(validation.dropna(subset=["p10", "p90", "actual"]))
    validation_rows = (
        pd.concat(cross_validated, ignore_index=True)
        if cross_validated
        else pd.DataFrame(columns=["actual", "p10", "p90"])
    )
    if validation_rows.empty:
        margin = 0.0
        coverage = None
        covered = 0
        total = 0
    else:
        nonconformity = np.maximum.reduce(
            [
                (validation_rows["p10"] - validation_rows["actual"]).to_numpy(),
                (validation_rows["actual"] - validation_rows["p90"]).to_numpy(),
                np.zeros(len(validation_rows)),
            ]
        )
        rank = min(
            len(nonconformity) - 1,
            int(math.ceil(0.80 * (len(nonconformity) + 1))) - 1,
        )
        margin = float(np.partition(nonconformity, rank)[rank])
        covered = int(
            (
                (validation_rows["actual"] >= validation_rows["p10"] - margin)
                & (validation_rows["actual"] <= validation_rows["p90"] + margin)
            ).sum()
        )
        total = len(validation_rows)
        coverage = float(covered / total)
    if not bands.empty:
        bands["p10"] = (bands["p10"] - margin).clip(lower=0)
        bands["p90"] = bands["p90"] + margin
        bands = bands.sort_values("startTime").reset_index(drop=True)
    return bands, {
        "covered": covered,
        "total": total,
        "coverage": coverage,
        "calibration_margin_mw": margin if total else None,
    }


def join_actuals(
    decision: pd.DataFrame, actuals: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Join decisions to actuals and calculate signed, absolute, and percent error."""
    forecast_column = _forecast_column(decision, "decision")
    _require_columns(decision, ["startTime"], "decision")
    _require_columns(actuals, ["startTime", "actual"], "actuals")
    decision_rows = decision.copy()
    if forecast_column != "generation":
        decision_rows = decision_rows.rename(columns={forecast_column: "generation"})
    actual_rows = actuals.copy()
    decision_rows["startTime"] = pd.to_datetime(decision_rows["startTime"], utc=True)
    actual_rows["startTime"] = pd.to_datetime(actual_rows["startTime"], utc=True)

    joined = decision_rows.merge(
        actual_rows[["startTime", "actual"]],
        on="startTime",
        how="outer",
        indicator=True,
        suffixes=("", "_actual"),
    )
    counts = {
        "decision_rows": int(len(decision_rows)),
        "actual_rows": int(len(actual_rows)),
        "matched": int((joined["_merge"] == "both").sum()),
        "decision_without_actual": int((joined["_merge"] == "left_only").sum()),
        "actual_without_decision": int((joined["_merge"] == "right_only").sum()),
    }
    joined = joined.loc[joined["_merge"] == "both"].drop(columns="_merge").copy()
    joined["generation"] = pd.to_numeric(joined["generation"], errors="coerce")
    joined["actual"] = pd.to_numeric(joined["actual"], errors="coerce")
    joined = joined.dropna(subset=["generation", "actual"])
    joined["error"] = joined["generation"] - joined["actual"]
    joined["abs_error"] = joined["error"].abs()
    joined["pct_error"] = joined["error"].div(joined["actual"].replace(0, np.nan))
    return joined.reset_index(drop=True), counts


def compute_metrics(df: pd.DataFrame) -> dict[str, int | float | None]:
    """Return standard forecast accuracy and signed-error metrics.

    MAPE is returned as a percentage; undefined metrics are ``None`` for empty
    input, and zero actual values are excluded from the MAPE denominator.
    """
    _require_columns(df, ["actual", "error", "abs_error"], "df")
    valid = df.dropna(subset=["actual", "error", "abs_error"])
    n = len(valid)
    if not n:
        return {
            "n": 0,
            "mae": None,
            "rmse": None,
            "bias": None,
            "mape": None,
            "p50": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "over_forecast_share": None,
            "under_forecast_share": None,
        }

    errors = valid["error"].astype(float)
    absolute_errors = valid["abs_error"].astype(float)
    nonzero_actual = valid.loc[valid["actual"] != 0]
    mape = (
        float((nonzero_actual["abs_error"] / nonzero_actual["actual"].abs()).mean() * 100)
        if not nonzero_actual.empty
        else None
    )
    return {
        "n": int(n),
        "mae": float(absolute_errors.mean()),
        "rmse": float(np.sqrt(np.square(errors).mean())),
        "bias": float(errors.mean()),
        "mape": mape,
        "p50": float(absolute_errors.quantile(0.50)),
        "p90": float(absolute_errors.quantile(0.90)),
        "p95": float(absolute_errors.quantile(0.95)),
        "p99": float(absolute_errors.quantile(0.99)),
        "over_forecast_share": float((errors > 0).mean()),
        "under_forecast_share": float((errors < 0).mean()),
    }


def compare_naive_baseline(df: pd.DataFrame, actuals: pd.DataFrame) -> dict[str, Any]:
    """Compare decision forecasts with the same half-hour's previous-day actual."""
    _require_columns(df, ["startTime", "actual", "generation"], "df")
    _require_columns(actuals, ["startTime", "actual"], "actuals")
    forecast_rows = df[["startTime", "actual", "generation"]].copy()
    forecast_rows["startTime"] = pd.to_datetime(forecast_rows["startTime"], utc=True)
    forecast_rows["generation"] = pd.to_numeric(forecast_rows["generation"], errors="coerce")

    baseline = actuals[["startTime", "actual"]].copy()
    baseline["startTime"] = pd.to_datetime(baseline["startTime"], utc=True)
    baseline["actual"] = pd.to_numeric(baseline["actual"], errors="coerce")
    baseline = baseline.rename(columns={"actual": "baseline"})
    baseline["startTime"] = baseline["startTime"] + pd.Timedelta(days=1)

    compared = forecast_rows.merge(baseline, on="startTime", how="inner")
    compared = compared.dropna(subset=["actual", "generation", "baseline"])
    if compared.empty:
        return {
            "n": 0,
            "mae_forecast": None,
            "mae_baseline": None,
            "skill_score": None,
        }
    forecast_mae = float((compared["generation"] - compared["actual"]).abs().mean())
    baseline_mae = float((compared["baseline"] - compared["actual"]).abs().mean())
    skill_score = (
        float(1 - forecast_mae / baseline_mae) if baseline_mae > 0 else None
    )
    return {
        "n": int(len(compared)),
        "mae_forecast": forecast_mae,
        "mae_baseline": baseline_mae,
        "skill_score": skill_score,
    }


def walk_forward_bias_correction(
    df: pd.DataFrame, min_training_samples: int = 1
) -> tuple[pd.DataFrame, dict[str, int | float | None]]:
    """Correct forecasts using only prior-day mean bias for each London hour."""
    if min_training_samples < 1:
        raise ValueError("min_training_samples must be at least one")
    _require_columns(df, ["startTime", "actual", "generation"], "df")
    columns = list(df.columns) + ["bias_correction", "corrected_forecast", "training_n"]
    if df.empty:
        return pd.DataFrame(columns=columns), {
            "n": 0,
            "mae_forecast": None,
            "mae_corrected": None,
            "mae_improvement": None,
            "mae_improvement_share": None,
        }

    result = df.copy()
    result["startTime"] = pd.to_datetime(result["startTime"], utc=True)
    result["actual"] = pd.to_numeric(result["actual"], errors="coerce")
    result["generation"] = pd.to_numeric(result["generation"], errors="coerce")
    result["delivery_date"] = (
        result["startTime"].dt.tz_convert(LONDON_TZ).dt.date
    )
    result["hour"] = result["startTime"].dt.tz_convert(LONDON_TZ).dt.hour
    result["bias_correction"] = np.nan
    result["corrected_forecast"] = np.nan
    result["training_n"] = 0

    for delivery_date in sorted(result["delivery_date"].unique()):
        test_mask = result["delivery_date"] == delivery_date
        train_mask = result["delivery_date"] < delivery_date
        history = result.loc[train_mask].copy()
        if history.empty:
            continue
        history["error"] = history["generation"] - history["actual"]
        stats = history.groupby("hour")["error"].agg(["mean", "count"])
        for index in result.index[test_mask]:
            hour = result.at[index, "hour"]
            if hour not in stats.index or stats.at[hour, "count"] < min_training_samples:
                continue
            correction = float(stats.at[hour, "mean"])
            result.at[index, "bias_correction"] = correction
            result.at[index, "corrected_forecast"] = max(
                0.0, float(result.at[index, "generation"] - correction)
            )
            result.at[index, "training_n"] = int(stats.at[hour, "count"])

    evaluated = result.dropna(subset=["actual", "generation", "corrected_forecast"]).copy()
    result = result.drop(columns=["delivery_date", "hour"])
    if evaluated.empty:
        return result, {
            "n": 0,
            "mae_forecast": None,
            "mae_corrected": None,
            "mae_improvement": None,
            "mae_improvement_share": None,
        }
    raw_mae = float((evaluated["generation"] - evaluated["actual"]).abs().mean())
    corrected_mae = float(
        (evaluated["corrected_forecast"] - evaluated["actual"]).abs().mean()
    )
    return result, {
        "n": int(len(evaluated)),
        "mae_forecast": raw_mae,
        "mae_corrected": corrected_mae,
        "mae_improvement": raw_mae - corrected_mae,
        "mae_improvement_share": (
            float((raw_mae - corrected_mae) / raw_mae) if raw_mae else None
        ),
    }


def error_by_wind_regime(df: pd.DataFrame) -> pd.DataFrame:
    """Report MAE, bias, and sample counts in low, medium, and high actual wind."""
    _require_columns(df, ["actual", "error", "abs_error"], "df")
    columns = ["regime", "actual_min", "actual_max", "mae", "bias", "n"]
    valid = df.dropna(subset=["actual", "error", "abs_error"]).copy()
    if valid.empty:
        return pd.DataFrame(columns=columns)
    if valid["actual"].nunique() == 1:
        valid["regime"] = "medium"
    else:
        regime_bins = min(3, int(valid["actual"].nunique()))
        codes, edges = pd.qcut(
            valid["actual"], q=regime_bins, labels=False, retbins=True, duplicates="drop"
        )
        labels = {
            1: ["medium"],
            2: ["low", "high"],
            3: ["low", "medium", "high"],
        }[len(edges) - 1]
        valid["regime"] = pd.Categorical(
            pd.Series(codes, index=valid.index).map(dict(enumerate(labels))),
            categories=["low", "medium", "high"],
            ordered=True,
        )
    result = (
        valid.groupby("regime", observed=True)
        .agg(
            actual_min=("actual", "min"),
            actual_max=("actual", "max"),
            mae=("abs_error", "mean"),
            bias=("error", "mean"),
            n=("error", "size"),
        )
        .reset_index()
    )
    result["regime"] = result["regime"].astype(str)
    result["n"] = result["n"].astype(int)
    return result[columns]


def error_by_day_hour(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize decision-forecast MAE by London delivery date and hour."""
    _require_columns(df, ["startTime", "error", "abs_error"], "df")
    columns = ["delivery_date", "hour", "mae", "bias", "n"]
    valid = df.dropna(subset=["error", "abs_error"]).copy()
    if valid.empty:
        return pd.DataFrame(columns=columns)
    local_times = pd.to_datetime(valid["startTime"], utc=True).dt.tz_convert(LONDON_TZ)
    valid["delivery_date"] = local_times.dt.strftime("%Y-%m-%d")
    valid["hour"] = local_times.dt.hour
    result = (
        valid.groupby(["delivery_date", "hour"], as_index=False)
        .agg(mae=("abs_error", "mean"), bias=("error", "mean"), n=("error", "size"))
    )
    result["n"] = result["n"].astype(int)
    return result[columns]


def analyze_ramp_events(
    decision: pd.DataFrame,
    actuals: pd.DataFrame,
    threshold_mw: float = 500.0,
) -> tuple[pd.DataFrame, dict[str, int | float | None]]:
    """Evaluate forecast direction and error on actual 30-minute wind ramps."""
    if threshold_mw <= 0:
        raise ValueError("threshold_mw must be greater than zero")
    forecast_column = _forecast_column(decision, "decision")
    _require_columns(decision, ["startTime"], "decision")
    _require_columns(actuals, ["startTime", "actual"], "actuals")
    forecasts = decision[["startTime", forecast_column]].rename(
        columns={forecast_column: "generation"}
    ).copy()
    forecasts["startTime"] = pd.to_datetime(forecasts["startTime"], utc=True)
    forecasts["generation"] = pd.to_numeric(forecasts["generation"], errors="coerce")
    actual_rows = actuals[["startTime", "actual"]].copy()
    actual_rows["startTime"] = pd.to_datetime(actual_rows["startTime"], utc=True)
    actual_rows["actual"] = pd.to_numeric(actual_rows["actual"], errors="coerce")

    previous_actuals = actual_rows.rename(
        columns={"startTime": "previous_startTime", "actual": "previous_actual"}
    )
    previous_actuals["startTime"] = (
        previous_actuals["previous_startTime"] + pd.Timedelta(minutes=30)
    )
    current = forecasts.merge(actual_rows, on="startTime", how="inner")
    current = current.merge(
        previous_actuals[["startTime", "previous_actual"]], on="startTime", how="inner"
    )
    current["previous_slot"] = current["startTime"] - pd.Timedelta(minutes=30)
    previous_forecasts = forecasts.rename(
        columns={
            "startTime": "previous_forecast_startTime",
            "generation": "previous_forecast",
        }
    )
    current = pd.merge_asof(
        current.sort_values("previous_slot"),
        previous_forecasts.sort_values("previous_forecast_startTime"),
        left_on="previous_slot",
        right_on="previous_forecast_startTime",
        direction="backward",
        tolerance=pd.Timedelta(minutes=90),
    )
    current["forecast_interval_minutes"] = (
        (current["startTime"] - current["previous_forecast_startTime"])
        .dt.total_seconds()
        .div(60)
    )
    current["actual_ramp"] = current["actual"] - current["previous_actual"]
    current["forecast_ramp"] = current["generation"] - current["previous_forecast"]
    events = current.loc[current["actual_ramp"].abs() >= threshold_mw].copy()
    events["forecast_error"] = events["generation"] - events["actual"]
    events["direction_caught"] = (
        (events["actual_ramp"] * events["forecast_ramp"]) > 0
    )
    event_frame = events.rename(columns={"generation": "forecast"})[
        [
            "startTime",
            "actual",
            "forecast",
            "previous_actual",
            "previous_forecast",
            "forecast_interval_minutes",
            "actual_ramp",
            "forecast_ramp",
            "forecast_error",
            "direction_caught",
        ]
    ].reset_index(drop=True)
    count = len(event_frame)
    available = event_frame.dropna(subset=["forecast_ramp"])
    caught = int(available["direction_caught"].sum())
    summary = {
        "threshold_mw": float(threshold_mw),
        "event_count": int(count),
        "forecast_direction_available": int(len(available)),
        "direction_caught": caught,
        "direction_caught_share": float(caught / len(available)) if len(available) else None,
        "mae_on_ramps": (
            float(event_frame["forecast_error"].abs().mean()) if count else None
        ),
    }
    return event_frame, summary


def error_by_horizon(
    forecasts: pd.DataFrame, actuals: pd.DataFrame, bin_hours: int = 6
) -> pd.DataFrame:
    """Summarize errors across all forecasts in consecutive horizon bins."""
    if bin_hours <= 0:
        raise ValueError("bin_hours must be greater than zero")
    _require_columns(forecasts, ["startTime", "publishTime"], "forecasts")
    forecast_column = _forecast_column(forecasts, "forecasts")
    _require_columns(actuals, ["startTime", "actual"], "actuals")
    forecast_rows = forecasts.copy()
    forecast_rows["startTime"] = pd.to_datetime(forecast_rows["startTime"], utc=True)
    forecast_rows["publishTime"] = pd.to_datetime(forecast_rows["publishTime"], utc=True)
    forecast_rows["horizon_h"] = (
        (forecast_rows["startTime"] - forecast_rows["publishTime"]).dt.total_seconds() / 3600
    )
    forecast_rows["forecast"] = pd.to_numeric(
        forecast_rows.pop(forecast_column), errors="coerce"
    )
    actual_rows = actuals.copy()
    actual_rows["startTime"] = pd.to_datetime(actual_rows["startTime"], utc=True)
    actual_rows["actual"] = pd.to_numeric(actual_rows["actual"], errors="coerce")
    joined = forecast_rows.merge(
        actual_rows[["startTime", "actual"]], on="startTime", how="inner"
    )
    joined = joined.dropna(subset=["forecast", "actual", "horizon_h"])
    joined = joined.loc[joined["horizon_h"] >= 0].copy()
    columns = ["horizon", "mae", "rmse", "bias", "n"]
    if joined.empty:
        return pd.DataFrame(columns=columns)

    max_horizon = float(joined["horizon_h"].max())
    bin_count = max(1, math.floor(max_horizon / bin_hours) + 1)
    edges = [index * bin_hours for index in range(bin_count + 1)]
    joined["horizon"] = pd.cut(
        joined["horizon_h"], bins=edges, right=False, include_lowest=True
    )
    rows: list[dict[str, Any]] = []
    for interval, group in joined.groupby("horizon", observed=True, sort=True):
        error = group["forecast"] - group["actual"]
        rows.append(
            {
                "horizon": f"{interval.left:g}-{interval.right:g}",
                "mae": float(error.abs().mean()),
                "rmse": float(np.sqrt(np.square(error).mean())),
                "bias": float(error.mean()),
                "n": int(len(group)),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def error_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize MAE and bias by London local hour of the target time."""
    _require_columns(df, ["startTime", "error", "abs_error"], "df")
    columns = ["hour", "mae", "bias", "n"]
    if df.empty:
        return pd.DataFrame(columns=columns)
    prepared = df.copy()
    prepared["startTime"] = pd.to_datetime(prepared["startTime"], utc=True)
    prepared["hour"] = prepared["startTime"].dt.tz_convert(LONDON_TZ).dt.hour
    result = (
        prepared.dropna(subset=["error", "abs_error"])
        .groupby("hour", as_index=False)
        .agg(mae=("abs_error", "mean"), bias=("error", "mean"), n=("error", "size"))
    )
    result["n"] = result["n"].astype(int)
    return result[columns]


def error_by_actual_level(df: pd.DataFrame, bins: int = 5) -> pd.DataFrame:
    """Summarize error by quantile buckets of actual generation."""
    if bins < 1:
        raise ValueError("bins must be at least 1")
    _require_columns(df, ["actual", "error", "abs_error"], "df")
    columns = ["actual_level", "mae", "bias", "n"]
    prepared = df.dropna(subset=["actual", "error", "abs_error"]).copy()
    if prepared.empty:
        return pd.DataFrame(columns=columns)
    if prepared["actual"].nunique() == 1:
        prepared["actual_level"] = "all"
    else:
        prepared["actual_level"] = pd.qcut(
            prepared["actual"], q=bins, duplicates="drop"
        ).astype(str)
    result = (
        prepared.groupby("actual_level", as_index=False, observed=True)
        .agg(mae=("abs_error", "mean"), bias=("error", "mean"), n=("error", "size"))
    )
    result["n"] = result["n"].astype(int)
    return result[columns]


def error_histogram(df: pd.DataFrame, bins: int = 30) -> list[dict[str, int | float]]:
    """Return a histogram of signed forecast errors."""
    if bins < 1:
        raise ValueError("bins must be at least 1")
    _require_columns(df, ["error"], "df")
    errors = pd.to_numeric(df["error"], errors="coerce").dropna().to_numpy(dtype=float)
    if not len(errors):
        return []
    counts, edges = np.histogram(errors, bins=bins)
    return [
        {
            "bin_start": float(edges[index]),
            "bin_end": float(edges[index + 1]),
            "count": int(counts[index]),
        }
        for index in range(len(counts))
    ]
