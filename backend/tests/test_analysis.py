import pandas as pd
import pytest

from backend.app.analysis import (
    analyze_ramp_events,
    add_cutoff,
    compare_naive_baseline,
    compute_metrics,
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
from datetime import date, timedelta


def test_select_decision_forecast_excludes_after_cutoff():
    forecasts = pd.DataFrame(
        {
            "startTime": ["2026-01-03T00:00:00Z", "2026-01-03T00:00:00Z"],
            "publishTime": ["2026-01-02T08:00:00Z", "2026-01-02T09:01:00Z"],
            "generation": [100, 200],
        }
    )

    result = select_decision_forecast(forecasts)

    assert result["generation"].tolist() == [100]


def test_select_decision_forecast_picks_latest_eligible():
    forecasts = pd.DataFrame(
        {
            "startTime": ["2026-01-03T00:00:00Z"] * 2,
            "publishTime": ["2026-01-02T07:00:00Z", "2026-01-02T09:00:00Z"],
            "generation": [100, 150],
        }
    )

    result = select_decision_forecast(forecasts)

    assert result["generation"].tolist() == [150]
    assert result.loc[0, "publishTime"] == pd.Timestamp("2026-01-02T09:00:00Z")


def test_cutoff_uses_london_local_time_in_winter_and_summer():
    forecasts = pd.DataFrame(
        {
            "startTime": ["2026-01-15T12:00:00Z", "2026-07-15T12:00:00Z"],
            "publishTime": ["2026-01-14T08:00:00Z", "2026-07-14T08:00:00Z"],
            "generation": [1, 2],
        }
    )

    result = add_cutoff(forecasts)

    assert result["cutoff"].tolist() == [
        pd.Timestamp("2026-01-14T09:00:00Z"),
        pd.Timestamp("2026-07-14T08:00:00Z"),
    ]
    assert result["horizon_h"].tolist() == [28.0, 28.0]


def test_join_actuals_counts_unmatched_rows_and_zero_actual_pct_is_null():
    decision = pd.DataFrame(
        {
            "startTime": ["2026-01-02T00:00:00Z", "2026-01-02T00:30:00Z"],
            "generation": [10, 5],
        }
    )
    actuals = pd.DataFrame(
        {
            "startTime": ["2026-01-02T00:00:00Z", "2026-01-02T01:00:00Z"],
            "actual": [0, 7],
        }
    )

    joined, counts = join_actuals(decision, actuals)

    assert pd.isna(joined.loc[0, "pct_error"])
    assert counts == {
        "decision_rows": 2,
        "actual_rows": 2,
        "matched": 1,
        "decision_without_actual": 1,
        "actual_without_decision": 1,
    }


def test_metrics_match_hand_calculated_errors():
    df = pd.DataFrame(
        {
            "actual": [100, 100, 100],
            "error": [10, -10, 20],
            "abs_error": [10, 10, 20],
        }
    )

    metrics = compute_metrics(df)

    assert metrics["n"] == 3
    assert metrics["mae"] == pytest.approx(40 / 3)
    assert metrics["rmse"] == pytest.approx((200) ** 0.5)
    assert metrics["bias"] == pytest.approx(20 / 3)
    assert metrics["mape"] == pytest.approx(40 / 3)
    assert metrics["p50"] == pytest.approx(10)
    assert metrics["over_forecast_share"] == pytest.approx(2 / 3)
    assert metrics["under_forecast_share"] == pytest.approx(1 / 3)


def test_cutoff_is_dst_safe_on_transition_day():
    forecasts = pd.DataFrame(
        {
            "startTime": ["2026-03-29T00:30:00Z"],
            "publishTime": ["2026-03-28T08:00:00Z"],
            "generation": [1],
        }
    )
    result = add_cutoff(forecasts)
    assert result.loc[0, "cutoff"] == pd.Timestamp("2026-03-28T09:00:00Z")


def test_error_summaries_handle_empty_and_constant_level_data():
    empty = pd.DataFrame(columns=["startTime", "actual", "error", "abs_error"])
    assert error_by_hour(empty).empty
    assert error_by_actual_level(empty).empty
    assert error_histogram(empty) == []
    assert error_by_actual_level(
        pd.DataFrame({"actual": [0, 0], "error": [1, -1], "abs_error": [1, 1]})
    )["actual_level"].tolist() == ["all"]


def test_error_by_horizon_uses_all_forecasts():
    forecasts = pd.DataFrame(
        {
            "startTime": ["2026-01-03T00:00:00Z"] * 2,
            "publishTime": ["2026-01-02T00:00:00Z", "2026-01-02T06:00:00Z"],
            "generation": [110, 90],
        }
    )
    actuals = pd.DataFrame(
        {"startTime": ["2026-01-03T00:00:00Z"], "actual": [100]}
    )

    result = error_by_horizon(forecasts, actuals, bin_hours=6)

    assert result["n"].tolist() == [1, 1]
    assert result["mae"].tolist() == [10, 10]


def test_uncertainty_bands_exclude_delivery_day_and_report_held_out_coverage():
    forecast_rows = []
    actual_rows = []
    start_day = date(2026, 1, 2)
    for day_index in range(30):
        target_day = start_day + timedelta(days=day_index)
        start_time = f"{target_day.isoformat()}T12:00:00Z"
        forecast_rows.append(
            {
                "startTime": start_time,
                "publishTime": f"{(target_day - timedelta(days=1)).isoformat()}T09:00:00Z",
                "forecast": 100 + day_index,
            }
        )
        if day_index < 29:
            actual_rows.append(
                {
                    "startTime": start_time,
                    "actual": 100 + day_index + (day_index % 5 - 2) * 10,
                }
            )

    bands, coverage = forecast_uncertainty(
        pd.DataFrame(forecast_rows),
        pd.DataFrame(actual_rows),
        date(2026, 1, 31),
        min_samples=3,
    )

    assert len(bands) == 1
    assert pd.isna(bands.loc[0, "actual"])
    assert bands.loc[0, "calibration_n"] >= 3
    assert bands.loc[0, "p10"] <= bands.loc[0, "p90"]
    assert coverage["total"] > 0
    assert coverage["coverage"] == pytest.approx(0.8, abs=0.1)
    assert coverage["calibration_margin_mw"] >= 0


def test_naive_baseline_matches_previous_day_half_hour_and_skill_score():
    actuals = pd.DataFrame(
        {
            "startTime": pd.to_datetime(
                [
                    "2026-01-02T10:00:00Z",
                    "2026-01-03T10:00:00Z",
                    "2026-01-02T10:30:00Z",
                    "2026-01-03T10:30:00Z",
                ],
                utc=True,
            ),
            "actual": [100, 120, 200, 150],
        }
    )
    decisions = pd.DataFrame(
        {
            "startTime": pd.to_datetime(
                ["2026-01-03T10:00:00Z", "2026-01-03T10:30:00Z"], utc=True
            ),
            "actual": [120, 150],
            "generation": [115, 160],
        }
    )

    result = compare_naive_baseline(decisions, actuals)

    assert result["n"] == 2
    assert result["mae_forecast"] == pytest.approx(7.5)
    assert result["mae_baseline"] == pytest.approx(35)
    assert result["skill_score"] == pytest.approx(1 - 7.5 / 35)


def test_walk_forward_bias_correction_trains_only_on_prior_days():
    rows = []
    for day, actual in [("2026-01-02", 100), ("2026-01-03", 100), ("2026-01-04", 100)]:
        rows.append(
            {
                "startTime": pd.Timestamp(f"{day}T10:00:00Z"),
                "actual": actual,
                "generation": 120,
            }
        )

    corrected, metrics = walk_forward_bias_correction(pd.DataFrame(rows))

    assert pd.isna(corrected.loc[0, "corrected_forecast"])
    assert corrected.loc[1, "training_n"] == 1
    assert corrected.loc[1, "corrected_forecast"] == pytest.approx(100)
    assert corrected.loc[2, "training_n"] == 2
    assert metrics["n"] == 2
    assert metrics["mae_forecast"] == pytest.approx(20)
    assert metrics["mae_corrected"] == pytest.approx(0)


def test_regime_split_and_day_hour_heatmap_return_expected_groups():
    joined = pd.DataFrame(
        {
            "startTime": pd.to_datetime(
                ["2026-01-02T00:00:00Z", "2026-01-02T01:00:00Z", "2026-01-03T00:00:00Z"],
                utc=True,
            ),
            "actual": [10, 20, 30],
            "error": [1, -2, 3],
            "abs_error": [1, 2, 3],
        }
    )

    regimes = error_by_wind_regime(joined)
    heatmap = error_by_day_hour(joined)

    assert regimes["regime"].tolist() == ["low", "medium", "high"]
    assert regimes["n"].sum() == 3
    assert len(heatmap) == 3
    assert heatmap["delivery_date"].tolist() == ["2026-01-02", "2026-01-02", "2026-01-03"]
    assert heatmap["hour"].tolist() == [0, 1, 0]


def test_ramp_event_detects_direction_when_forecast_moves_same_way():
    actuals = pd.DataFrame(
        {
            "startTime": pd.to_datetime(
                ["2026-01-02T10:00:00Z", "2026-01-02T10:30:00Z"], utc=True
            ),
            "actual": [100, 800],
        }
    )
    decision = pd.DataFrame(
        {
            "startTime": pd.to_datetime(
                ["2026-01-02T10:00:00Z", "2026-01-02T10:30:00Z"], utc=True
            ),
            "generation": [120, 700],
        }
    )

    events, summary = analyze_ramp_events(decision, actuals, threshold_mw=500)

    assert len(events) == 1
    assert events.loc[0, "actual_ramp"] == 700
    assert events.loc[0, "forecast_ramp"] == 580
    assert events.loc[0, "direction_caught"]
    assert summary["direction_caught_share"] == 1
