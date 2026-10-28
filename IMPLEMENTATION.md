# IMPLEMENTATION.md: Wind Forecast Monitoring App (for GitHub Copilot)

> Usage: open this file in VS Code, then in Copilot Chat say
> *"Follow IMPLEMENTATION.md. Implement Step N."* one step at a time.
> To make Copilot always see it, copy it to `.github/copilot-instructions.md`.

## 0. Context

A UK energy utility buys power on the **day-ahead market**. Decisions are made on day **D-1** for delivery on day **D**. Wind output is weather-dependent, so the trading team needs to know:

1. **The latest wind forecast available at decision time** (the most recent forecast published *before* the D-1 cutoff).
2. **How accurate those forecasts have been**, in numbers, so they can allow for the error.

Scope: national-level GB wind only, Elexon data only, **decisions made in January 2026**.

| Dataset | Endpoint | Filter used | Fields used |
|---|---|---|---|
| Actuals (FUELHH) | `https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream` | `settlementDateFrom/To`, `fuelType=WIND` | `startTime`, `generation` |
| Forecasts (WINDFOR) | `https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream` | `publishDateTimeFrom/To` (no filter = latest only) | `startTime`, `publishTime`, `generation` |

## 1. Stack and constraints

- Backend: **Python 3.11 + FastAPI + pandas**
- Frontend: **React (Vite) + Recharts**
- **Docker** for both; deploy to **Vercel or Heroku**
- The deployed app must **not call Elexon at runtime**. It reads pre-fetched CSVs from `backend/data/processed/`.
- Time budget: 16 hours. Prefer simple and correct over clever.
- README must say that AI tools were used.

## 2. Repository layout

```
<anon-repo-name>/
├── README.md
├── IMPLEMENTATION.md
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── data_fetcher.py     # DONE: fetch, retry, cache, clean
│   │   ├── analysis.py         # Step 2: decision-time logic + metrics
│   │   ├── main.py             # Step 3: FastAPI routes
│   │   └── schemas.py          # Step 3: Pydantic response models
│   ├── data/
│   │   ├── cache/              # raw per-chunk CSVs (gitignored)
│   │   └── processed/          # wind_actuals.csv, wind_forecasts.csv (committed)
│   └── tests/
│       └── test_analysis.py    # Step 2
└── frontend/
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── api.js
        ├── App.jsx
        └── components/
            ├── ControlsBar.jsx
            ├── ForecastVsActualChart.jsx
            ├── MetricsCards.jsx
            ├── ErrorByHorizonChart.jsx
            ├── ErrorByHourChart.jsx
            └── ErrorHistogram.jsx
```

## 3. Steps

### Step 1: Data fetching (DONE)

`backend/app/data_fetcher.py` already provides:

- `load_january_2026(refresh=False) -> (actuals_df, forecasts_df)`
- `save_processed(...)` and `read_processed()`
- Run with `python -m app.data_fetcher` from `backend/`.

Output schemas (all datetimes are tz-aware UTC):

- `actuals`: `startTime`, `actual` (MW)
- `forecasts`: `startTime`, `publishTime`, `forecast` (MW)

Do not modify this module unless the real API behaves differently from what is assumed. Notes: it was only tested with a mocked API, so run it against the real API first and check the row counts.

### Step 2: Analysis (`backend/app/analysis.py`)

**Key concept.** One target half-hour (`startTime`) has many forecasts, each with a different `publishTime`. For a day-ahead decision, pick, per `startTime`, the **latest forecast with `publishTime <= cutoff`**, where:

```
cutoff = (local date of startTime) - 1 day, at CUTOFF_HOUR:CUTOFF_MINUTE  (Europe/London)
default CUTOFF = 09:00 London time on D-1  (conservative; day-ahead auction gates close ~09:30-10:20)
```

Implement these pure functions (no I/O, easy to unit-test):

```python
def add_cutoff(forecasts: pd.DataFrame, cutoff_hour: int = 9, cutoff_minute: int = 0) -> pd.DataFrame:
    """Add 'cutoff' (UTC) and 'horizon_h' = (startTime - publishTime) in hours.
    Compute the London local date with tz_convert('Europe/London'), build the
    cutoff as a London-local timestamp (D-1 at hh:mm), then convert it to UTC."""

def select_decision_forecast(forecasts: pd.DataFrame, cutoff_hour: int = 9, cutoff_minute: int = 0) -> pd.DataFrame:
    """For each startTime keep the latest row with publishTime <= cutoff.
    Targets with no eligible forecast are dropped (report the count)."""

def join_actuals(decision: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Inner join on startTime. Add error = forecast - actual, abs_error, pct_error
    (pct_error = error / actual, NaN where actual == 0). Return the join plus a
    dict of dropped-row counts."""

def compute_metrics(df: pd.DataFrame) -> dict:
    """n, mae, rmse, bias (mean error), mape (ignore actual==0), p50/p90/p95/p99 of abs_error,
    over_forecast_share (error > 0), under_forecast_share (error < 0)."""

def error_by_horizon(forecasts: pd.DataFrame, actuals: pd.DataFrame, bin_hours: int = 6) -> pd.DataFrame:
    """Use ALL forecasts (not just the decision one), join to actuals, bucket horizon_h
    into bins (0-6, 6-12, ... up to the max). Return mae, rmse, bias, n per bin."""

def error_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    """Group by London hour of the target time (0-23) -> mae, bias, n."""

def error_by_actual_level(df: pd.DataFrame, bins: int = 5) -> pd.DataFrame:
    """Quantile-bin actual generation -> mae, bias, n. Shows whether the error grows with output."""

def error_histogram(df: pd.DataFrame, bins: int = 30) -> list[dict]:
    """Histogram of signed error: [{'bin_start':..,'bin_end':..,'count':..}]."""
```

**Tests** (`tests/test_analysis.py`, pytest). Cover at least:

1. A forecast published *after* the cutoff is never selected.
2. When two forecasts are eligible, the later `publishTime` wins.
3. The cutoff is correct across the January timezone (London = UTC in winter; also add a summer-time test case so the code is DST-safe).
4. Metrics match hand-computed values on a tiny dataset (e.g. errors `[10, -10, 20]`).
5. `actual == 0` does not crash `pct_error`.

### Step 3: API (`backend/app/main.py`)

FastAPI app. Load `read_processed()` once at startup. Enable CORS (configurable via env var `CORS_ORIGINS`). All endpoints accept optional `cutoff_hour` (default 9), `cutoff_minute` (default 0), `start`, `end` (target dates, `YYYY-MM-DD`, validated against the January 2026 range).

| Route | Returns |
|---|---|
| `GET /api/health` | `{status: "ok", rows: {...}}` |
| `GET /api/config` | Date range, default cutoff, data coverage, last publishTime |
| `GET /api/forecast-vs-actual` | Rows `{startTime, forecast, actual, publishTime, horizon_h, error}` for the date range |
| `GET /api/metrics` | `compute_metrics` output plus counts of dropped rows |
| `GET /api/error-by-horizon` | `error_by_horizon` |
| `GET /api/error-by-hour` | `error_by_hour` |
| `GET /api/error-by-level` | `error_by_actual_level` |
| `GET /api/error-histogram` | `error_histogram` |
| `GET /api/latest-forecast` | The forecast a trader would have for a chosen **delivery date**: all 48 half-hours from the latest pre-cutoff publish, plus that publish time |

Return ISO-8601 UTC strings. Pydantic models in `schemas.py`. Return 422 with a clear message for invalid input. Never return NaN in JSON (convert to `null`).

### Step 4: Frontend (React + Vite + Recharts)

Single-page dashboard, top to bottom:

1. **ControlsBar**: delivery-date range pickers (limited to Jan 2026), cutoff time selector (default 09:00), a short plain-English line: *"Showing forecasts as they stood at 09:00 on the day before delivery."*
2. **MetricsCards**: MAE, RMSE, Bias (with a hint: positive = over-forecasting), P90 and P99 abs error, sample size. Show units (MW) and a one-line tooltip for each.
3. **ForecastVsActualChart**: line chart of forecast and actual over time, with an optional error band.
4. **ErrorByHorizonChart**: bar chart of MAE by forecast horizon bucket (shows how forecasts improve nearer delivery).
5. **ErrorByHourChart** and **ErrorHistogram**.
6. **"Buying guidance" panel**: derived only from the data, e.g. *"Based on January 2026, the day-ahead wind forecast was within ±X MW 90% of the time. Consider holding a buffer of about Y MW against under-delivery."* Compute from the percentiles of the signed error and say clearly that it is historical, not a guarantee.

Requirements: loading and error states, responsive layout, accessible colours, API base URL from `VITE_API_URL`.

### Step 5: Docker

- `backend/Dockerfile`: `python:3.11-slim`, install requirements, run `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`.
- `frontend/Dockerfile`: multi-stage build (node, then nginx serving `dist/`).
- `docker-compose.yml`: both services, frontend on `:3000`, backend on `:8000`.

### Step 6: Deployment

Pick one:

- **Heroku (simplest with Docker):** two apps, or one app where FastAPI serves the built frontend as static files (use this to keep a single URL). Use `heroku.yml` with `build: docker`.
- **Vercel:** frontend on Vercel, backend as a separate service (Vercel Python functions have size and timeout limits; pandas is heavy). If so, deploy the backend on Heroku/Render and set `VITE_API_URL`.

Commit `data/processed/*.csv` so deployment needs no Elexon access. Open the final URL in an incognito window to verify.

### Step 7: README

Include: project purpose; directory description; how to run locally (`python -m app.data_fetcher`, `uvicorn app.main:app --reload`, `npm run dev`, or `docker compose up`); the live link; **a statement that AI tools (GitHub Copilot, Claude) were used**; the assumptions (cutoff, timezone, January interpretation); known limitations.

## 4. Assumptions to state in README and video

1. **Cutoff** is 09:00 London time on D-1 (configurable).
2. "Decisions made in January 2026" means D-1 in January, so delivery days run **2 Jan to 1 Feb 2026**. This is configurable in `data_fetcher.py` (`DECISION_START/END`).
3. Actual wind is FUELHH `generation` (30-minute average MW); forecast error = forecast - actual (positive means over-forecast).
4. Forecast horizon = `startTime - publishTime`.
5. Half-hours without an eligible forecast or without an actual are excluded and counted.

## 5. Coding standards

- Type hints and docstrings on all public functions; keep functions small and pure where possible.
- No secrets in the repo. Config via environment variables.
- `pytest` must pass; format with `black` (backend) and `prettier` (frontend).
- Small, meaningful commits.

## 6. Video checklist (max 10 minutes)

**Part 1, customer pitch (about 4-5 min):** the problem in their words; a live demo of "what forecast do I have at 09:00 tomorrow's decision"; the headline accuracy numbers; one insight (e.g. error vs horizon, or worst hours); the buying-guidance panel; the value and next steps.

**Part 2, technical review (about 4-5 min):** architecture diagram; the decision-time logic and why `publishTime <= cutoff` matters; data pipeline (chunking, retries, cache, no runtime API calls); metrics choices; tests; Docker and deployment; limitations and next steps.
