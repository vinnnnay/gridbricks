# Gridbricks · Wind Forecast Monitor

> A day-ahead GB wind forecast dashboard for exploring forecast accuracy, uncertainty, revisions, and trading buffers.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Run-Docker-2496ED?logo=docker&logoColor=white)

The dashboard compares the latest forecast available by a day-ahead decision cutoff with delivered GB wind generation. It uses preprocessed Elexon CSV data; **the deployed API does not call Elexon at runtime**.

## What it does

| Feature | What you can explore |
| --- | --- |
| Forecast accuracy | Forecast vs. actual, MAE, RMSE, bias, error percentiles, and error distributions |
| Uncertainty bands | Historical P10–P90 wind-output range conditioned on forecast horizon and output level, with held-out coverage |
| Thermal buffer calculator | Enter expected demand and compare the expected wind gap with a P10-based planning buffer |
| Forecast value | Compare forecast MAE with a same-half-hour-yesterday baseline and calculate a skill score |
| Walk-forward correction | Compare raw MAE with an hourly bias-corrected forecast trained only on prior delivery days |
| Cutoff sensitivity | Compare forecast MAE for London decision cutoffs from 06:00 to 12:00 |
| Ramp events | Inspect large half-hour wind changes and whether the forecast direction matched |
| Wind regimes | Compare error across low, medium, and high actual wind output |
| Day × hour heatmap | See how forecast MAE varies by London delivery date and hour |
| Forecast revisions | Follow the published forecast versions for a selected delivery day |

## Run with Docker

### Prerequisites

- Docker Desktop with Docker Compose
- The processed CSV files in `backend/data/processed/`:
  - `wind_actuals.csv`
  - `wind_forecasts.csv`

Those files are present in this project workspace. To regenerate them from Elexon, use the data setup steps below.

### Start the app

From the project root:

```powershell
docker compose up --build -d
```

Open the dashboard at **[http://localhost:3000](http://localhost:3000)**. The API is available at [http://localhost:8000](http://localhost:8000), with interactive API documentation at [http://localhost:8000/docs](http://localhost:8000/docs).

Check service status and logs:

```powershell
docker compose ps
docker compose logs -f
```

Stop the app:

```powershell
docker compose down
```

## Data setup and refresh

The project covers January 2026 day-ahead decisions. Generate or refresh the processed CSVs from the project root:

```powershell
Set-Location backend
py -3.11 -m pip install -r ..\requirements.txt
py -3.11 ..\data_fetcher.py
```

Use `--refresh` to ignore the chunk cache and download the data again:

```powershell
py -3.11 ..\data_fetcher.py --refresh
```

The fetcher writes cleaned files to `backend/data/processed/`. Docker Compose mounts that directory read-only into the API container.

## Run locally without Docker

Start the API in one terminal:

```powershell
py -3.11 -m pip install -r requirements.txt
Set-Location backend
py -3.11 -m uvicorn app.main:app --reload
```

Start the frontend in another terminal:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Open the Vite URL printed in the terminal (usually [http://localhost:5173](http://localhost:5173)). The Vite development server proxies API requests to `http://localhost:8000`.

## Test and build

Run the backend tests:

```powershell
py -3.11 -m pytest backend\tests -q
```

Build the frontend:

```powershell
Set-Location frontend
npm ci
npm run build
```

The backend tests can also run inside the built Docker image:

```powershell
docker run --rm -v "${PWD}:/work" -w /work gridbricks-backend python -m pytest backend/tests -q
```

## API overview

All API routes are under `/api`.

| Route | Purpose |
| --- | --- |
| `/health` | Service status and loaded row counts |
| `/config` | Supported dates, defaults, and data coverage |
| `/forecast-vs-actual` | Decision-time forecast and actual observations |
| `/metrics` | Forecast accuracy metrics and dropped-row counts |
| `/latest-forecast` | Latest eligible forecast and P10–P90 estimates for a delivery date |
| `/naive-baseline` | Forecast skill vs. previous-day actual generation |
| `/bias-correction` | Walk-forward, hour-of-day bias correction |
| `/cutoff-sensitivity` | MAE at decision cutoffs from 06:00 to 12:00 |
| `/ramp-events` | Actual wind ramps and forecast direction results |
| `/error-by-horizon`, `/error-by-hour`, `/error-by-level` | Forecast error breakdowns |
| `/error-by-regime` | Error across low, medium, and high wind regimes |
| `/error-heatmap` | MAE by London delivery date and hour |
| `/error-histogram` | Signed forecast-error histogram |
| `/forecast-revisions` | Forecast publish versions for a delivery date |

## Data assumptions and interpretation

- **Period:** “Decisions made in January 2026” means decision days 1–31 January. Delivery dates therefore run from **2 January through 1 February 2026**.
- **Decision cutoff:** Defaults to **09:00 Europe/London on D-1**. The forecast used is the latest one published at or before that cutoff.
- **Actuals:** FUELHH `generation`, representing 30-minute average MW.
- **Forecast error:** `forecast − actual`; positive error means over-forecasting.
- **Forecast horizon:** Target `startTime − publishTime`.
- **Missing observations:** Targets without an eligible forecast or actual are excluded from matched metrics and counted where applicable.
- **Uncertainty bands:** Historical actual-minus-forecast residuals are grouped by horizon and forecast output. The selected delivery day is excluded from calibration; held-out coverage is empirical and is not guaranteed to equal 80%.
- **Bias correction:** Uses only earlier delivery days and the target's London hour to avoid training on the test day.
- **Naïve baseline:** Uses the actual generation from the previous day at the same half-hour where that observation is available.
- **Ramp events:** Default threshold is a 500 MW actual change between adjacent half-hours. As the forecast data can be hourly, the closest earlier forecast target within 90 minutes is used to assess direction; the interval is shown.
- **Wind regimes:** Low, medium, and high are actual-generation terciles calculated over the selected period.
- **Planning guidance:** The demand input is user-provided. Thermal buffer estimates are historical planning aids, not dispatch advice or a guarantee of supply.

## Deployment status

The app is verified for local Docker use. It is **not yet publicly deployed**. A hosted deployment needs the processed CSVs in its build or mounted data volume, plus appropriate frontend/API URLs and CORS origins when the services use separate domains. No live URL is configured yet.

### Vercel FastAPI entrypoint

The repository root contains a `pyproject.toml` that declares the API's Python
dependencies and points Vercel to the FastAPI application at
`backend.app.main:app`. The `.python-version` file selects Python 3.11. In
Vercel, set the project **Root Directory** to the repository root (not
`backend/`) so Vercel can read this
configuration and the `backend/` package. Ensure
`backend/data/processed/wind_actuals.csv` and
`backend/data/processed/wind_forecasts.csv` are committed and included in the
deployment. Configure `CORS_ORIGINS` for the deployed frontend origin when it
does not share the API's origin.

## Project structure

```text
.
├── backend/
│   ├── app/                 # FastAPI routes, response schemas, and analysis
│   ├── data/
│   │   ├── cache/           # Raw chunk cache (ignored by Git)
│   │   └── processed/       # Cleaned CSVs used by the app
│   ├── tests/               # Analysis and API tests
│   └── Dockerfile
├── frontend/
│   ├── src/                 # React dashboard and charts
│   └── Dockerfile
├── data_fetcher.py
├── docker-compose.yml
├── IMPLEMENTATION.md
└── requirements.txt
```

## AI assistance

AI tools, including GitHub Copilot, were used to assist with implementation and documentation.
