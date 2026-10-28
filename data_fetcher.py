"""Elexon BMRS data fetching for the wind forecast app.

Features
- Chunked requests (small windows are friendlier to the API)
- Retries with exponential backoff (handles 429 / 5xx, honours Retry-After)
- Per-chunk CSV cache so an interrupted run resumes where it stopped
- Cleaning: UTC datetimes, de-duplication, WIND-only actuals

Datasets
- FUELHH  (actuals):   filtered by settlement date, fuelType=WIND
- WINDFOR (forecasts): filtered by publish time (no filter = latest only)

Run from the backend/ folder:
    python -m app.data_fetcher                # fetch + cache January 2026 decisions
    python -m app.data_fetcher --refresh      # ignore cache, re-download
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
CACHE_DIR = Path(os.environ.get("CACHE_DIR", "data/cache"))
PROCESSED_DIR = Path(os.environ.get("PROCESSED_DIR", "data/processed"))

# "Decisions made in January 2026" => the decision day D-1 falls in January,
# so delivery (target) days run from 2026-01-02 to 2026-02-01.
# Change these if you interpret the brief differently.
DECISION_START = date(2026, 1, 1)
DECISION_END = date(2026, 1, 31)

REQUEST_TIMEOUT = 60          # seconds
PAUSE_BETWEEN_CALLS = 0.25    # seconds, polite spacing to avoid 429s

ACTUAL_COLS = ["startTime", "settlementDate", "settlementPeriod", "publishTime", "generation"]
FORECAST_COLS = ["startTime", "publishTime", "generation"]


# --------------------------------------------------------------------------
# HTTP session with retries
# --------------------------------------------------------------------------
def make_session() -> requests.Session:
    retry = Retry(
        total=6,
        backoff_factor=1.5,                       # 0s, 1.5s, 3s, 6s, ...
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"Accept": "application/json"})
    return s


def get_json(session: requests.Session, endpoint: str, params: dict) -> list[dict]:
    """GET <BASE_URL>/<endpoint> and return the parsed JSON list."""
    url = f"{BASE_URL}/{endpoint}"
    resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    if resp.status_code == 400:
        raise ValueError(f"Bad request to {url} with {params}: {resp.text[:300]}")
    resp.raise_for_status()
    time.sleep(PAUSE_BETWEEN_CALLS)
    data = resp.json()
    # Stream endpoints return a bare list; be defensive in case of {"data": [...]}
    return data["data"] if isinstance(data, dict) and "data" in data else data


# --------------------------------------------------------------------------
# Chunking + cache helpers
# --------------------------------------------------------------------------
def iter_windows(start: datetime, end: datetime, step: timedelta) -> Iterator[tuple[datetime, datetime]]:
    """Yield consecutive [from, to) windows covering [start, end)."""
    cur = start
    while cur < end:
        nxt = min(cur + step, end)
        yield cur, nxt
        cur = nxt


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cached_fetch(cache_file: Path, fetch: Callable[[], list[dict]],
                  columns: list[str], refresh: bool) -> pd.DataFrame:
    """Return the chunk from cache if present, else fetch and store it."""
    if cache_file.exists() and not refresh:
        return pd.read_csv(cache_file)
    rows = fetch()
    df = pd.DataFrame(rows)
    for c in columns:                      # keep a stable schema even when empty
        if c not in df.columns:
            df[c] = pd.NA
    df = df[columns]
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_file, index=False)
    return df


# --------------------------------------------------------------------------
# Actuals: FUELHH (WIND)
# --------------------------------------------------------------------------
def fetch_actuals(start: date, end: date, chunk_days: int = 7,
                  refresh: bool = False, session: requests.Session | None = None) -> pd.DataFrame:
    """Wind actuals for settlement dates start..end (inclusive).

    Returns columns: startTime (UTC), actual (MW, 30-min average).
    """
    session = session or make_session()
    frames = []
    d = start
    while d <= end:
        chunk_end = min(d + timedelta(days=chunk_days - 1), end)
        cache_file = CACHE_DIR / f"fuelhh_wind_{d}_{chunk_end}.csv"
        params = {
            "settlementDateFrom": d.isoformat(),
            "settlementDateTo": chunk_end.isoformat(),
            "fuelType": ["WIND"],
        }
        log.info("FUELHH %s -> %s", d, chunk_end)
        frames.append(_cached_fetch(
            cache_file, lambda p=params: get_json(session, "FUELHH/stream", p),
            ACTUAL_COLS, refresh))
        d = chunk_end + timedelta(days=1)

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=ACTUAL_COLS)
    return clean_actuals(df)


def clean_actuals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["startTime", "actual"])
    df = df.copy()
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df = (df.dropna(subset=["startTime", "generation"])
            .sort_values("publishTime")
            .drop_duplicates("startTime", keep="last")     # overlapping chunks / revisions
            .sort_values("startTime"))
    return df[["startTime", "generation"]].rename(columns={"generation": "actual"}).reset_index(drop=True)


# --------------------------------------------------------------------------
# Forecasts: WINDFOR
# --------------------------------------------------------------------------
def fetch_forecasts(publish_from: datetime, publish_to: datetime, chunk_hours: int = 24,
                    refresh: bool = False, session: requests.Session | None = None) -> pd.DataFrame:
    """All WINDFOR forecasts published in [publish_from, publish_to).

    Without publish filters the API only returns the latest forecast, so the
    publish window is mandatory for history.
    Returns columns: startTime, publishTime (both UTC), forecast (MW).
    """
    session = session or make_session()
    frames = []
    for w_from, w_to in iter_windows(publish_from, publish_to, timedelta(hours=chunk_hours)):
        cache_file = CACHE_DIR / f"windfor_{_iso(w_from)}_{_iso(w_to)}.csv".replace(":", "")
        params = {"publishDateTimeFrom": _iso(w_from), "publishDateTimeTo": _iso(w_to)}
        log.info("WINDFOR %s -> %s", params["publishDateTimeFrom"], params["publishDateTimeTo"])
        frames.append(_cached_fetch(
            cache_file, lambda p=params: get_json(session, "WINDFOR/stream", p),
            FORECAST_COLS, refresh))

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=FORECAST_COLS)
    return clean_forecasts(df)


def clean_forecasts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["startTime", "publishTime", "forecast"])
    df = df.copy()
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df = (df.dropna(subset=["startTime", "publishTime", "generation"])
            .drop_duplicates(["startTime", "publishTime"], keep="last")
            .sort_values(["startTime", "publishTime"]))
    return (df[["startTime", "publishTime", "generation"]]
            .rename(columns={"generation": "forecast"}).reset_index(drop=True))


# --------------------------------------------------------------------------
# One-call loader used by the API + CLI
# --------------------------------------------------------------------------
def load_january_2026(refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch (or read from cache) everything needed for Jan-2026 decisions."""
    session = make_session()
    publish_from = datetime.combine(DECISION_START, dtime.min, tzinfo=timezone.utc)
    publish_to = datetime.combine(DECISION_END + timedelta(days=1), dtime.min, tzinfo=timezone.utc)
    forecasts = fetch_forecasts(publish_from, publish_to, refresh=refresh, session=session)
    # Target days = decision day + 1
    actuals = fetch_actuals(DECISION_START + timedelta(days=1),
                            DECISION_END + timedelta(days=1),
                            refresh=refresh, session=session)
    return actuals, forecasts


def save_processed(actuals: pd.DataFrame, forecasts: pd.DataFrame) -> None:
    """Persist cleaned data so the deployed app never calls Elexon at runtime."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    actuals.to_csv(PROCESSED_DIR / "wind_actuals.csv", index=False)
    forecasts.to_csv(PROCESSED_DIR / "wind_forecasts.csv", index=False)


def read_processed() -> tuple[pd.DataFrame, pd.DataFrame]:
    actuals = pd.read_csv(PROCESSED_DIR / "wind_actuals.csv", parse_dates=["startTime"])
    forecasts = pd.read_csv(PROCESSED_DIR / "wind_forecasts.csv", parse_dates=["startTime", "publishTime"])
    return actuals, forecasts


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Elexon wind data (Jan 2026 decisions)")
    parser.add_argument("--refresh", action="store_true", help="ignore the cache and re-download")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    actuals, forecasts = load_january_2026(refresh=args.refresh)
    save_processed(actuals, forecasts)
    log.info("Actuals: %d rows (%s -> %s)", len(actuals), actuals.startTime.min(), actuals.startTime.max())
    log.info("Forecasts: %d rows (%s -> %s published)", len(forecasts),
             forecasts.publishTime.min(), forecasts.publishTime.max())


if __name__ == "__main__":
    main()
