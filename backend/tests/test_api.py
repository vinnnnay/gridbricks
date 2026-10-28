from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import HTTPException

from backend.app import main


@pytest.fixture
def api_request():
    actuals = pd.DataFrame(
        {
            "startTime": pd.to_datetime(
                ["2026-01-03T00:00:00Z", "2026-01-03T00:30:00Z"], utc=True
            ),
            "actual": [100, 0],
        }
    )
    forecasts = pd.DataFrame(
        {
            "startTime": pd.to_datetime(
                [
                    "2026-01-03T00:00:00Z",
                    "2026-01-03T00:00:00Z",
                    "2026-01-03T00:00:00Z",
                    "2026-01-03T00:30:00Z",
                    "2026-01-03T00:30:00Z",
                ],
                utc=True,
            ),
            "publishTime": pd.to_datetime(
                [
                    "2026-01-02T08:00:00Z",
                    "2026-01-02T09:00:00Z",
                    "2026-01-02T09:01:00Z",
                    "2026-01-02T08:00:00Z",
                    "2026-01-02T09:00:00Z",
                ],
                utc=True,
            ),
            "forecast": [95, 110, 1000, 3, 5],
        }
    )
    state = SimpleNamespace(actuals=actuals, forecasts=forecasts)
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_health_and_config_report_loaded_data(api_request):
    health = main.health(api_request)
    config = main.config(api_request)

    assert health == {"status": "ok", "rows": {"actuals": 2, "forecasts": 5}}
    assert config["start_date"] == "2026-01-02"
    assert config["end_date"] == "2026-02-01"
    assert config["last_publish_time"] == "2026-01-02T09:01:00Z"


def test_forecast_endpoint_uses_latest_pre_cutoff_forecast(api_request):
    result = main.forecast_vs_actual(
        api_request, 9, 0, date(2026, 1, 3), date(2026, 1, 3)
    )

    assert [row["forecast"] for row in result] == [110, 5]
    assert [row["error"] for row in result] == [10, 5]
    assert all(row["publishTime"] == "2026-01-02T09:00:00Z" for row in result)


def test_metrics_include_zero_actual_and_row_drop_counts(api_request):
    result = main.metrics(api_request, 9, 0, date(2026, 1, 3), date(2026, 1, 3))

    assert result["n"] == 2
    assert result["mae"] == pytest.approx(7.5)
    assert result["dropped_rows"]["targets_without_eligible_forecast"] == 0
    assert result["dropped_rows"]["decision_without_actual"] == 0


def test_latest_forecast_returns_shared_latest_publish(api_request):
    result = main.latest_forecast(api_request, date(2026, 1, 3), 9, 0)

    assert result["publishTime"] == "2026-01-02T09:00:00Z"
    assert result["cutoff"] == "2026-01-02T09:00:00Z"
    assert result["count"] == 2
    assert [row["forecast"] for row in result["rows"]] == [110, 5]


def test_routes_validate_requested_january_range(api_request):
    with pytest.raises(HTTPException) as error:
        main.metrics(api_request, 9, 0, date(2026, 1, 1), date(2026, 1, 3))

    assert error.value.status_code == 422


def test_cutoff_sensitivity_returns_all_hours_from_six_to_twelve(api_request):
    rows = main.cutoff_sensitivity(api_request, 0, date(2026, 1, 3), date(2026, 1, 3))

    assert [row["cutoff_hour"] for row in rows] == list(range(6, 13))
    assert rows[0]["n"] == 0
    assert rows[-1]["n"] == 2


def test_revision_tracker_returns_every_publish_version(api_request):
    result = main.forecast_revisions(api_request, date(2026, 1, 3))

    assert result["revision_count"] == 3
    assert len(result["revisions"]) == 3
    assert len(result["actuals"]) == 2


def test_new_comparison_regime_heatmap_and_ramp_endpoints(api_request):
    start = date(2026, 1, 3)
    end = date(2026, 1, 3)

    baseline = main.naive_baseline(api_request, 9, 0, start, end)
    bias = main.bias_correction(api_request, 9, 0, start, end)
    regimes = main.api_error_by_regime(api_request, 9, 0, start, end)
    heatmap = main.api_error_heatmap(api_request, 9, 0, start, end)
    ramps = main.ramp_events(api_request, 9, 0, start, end, 100)

    assert baseline["n"] == 0
    assert bias["n"] == 0
    assert sum(row["n"] for row in regimes) == 2
    assert len(heatmap) == 1
    assert heatmap[0]["n"] == 2
    assert ramps["summary"]["threshold_mw"] == 100
