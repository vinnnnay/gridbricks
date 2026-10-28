import { useCallback, useEffect, useState } from "react";
import { getConfig, getDashboardData } from "./api.js";
import BuyingGuidance from "./components/BuyingGuidance.jsx";
import ErrorHeatmap from "./components/ErrorHeatmap.jsx";
import BufferCalculator from "./components/BufferCalculator.jsx";
import ControlsBar from "./components/ControlsBar.jsx";
import CutoffSensitivityChart from "./components/CutoffSensitivityChart.jsx";
import ErrorByHourChart from "./components/ErrorByHourChart.jsx";
import ErrorByHorizonChart from "./components/ErrorByHorizonChart.jsx";
import ErrorHistogram from "./components/ErrorHistogram.jsx";
import ForecastVsActualChart from "./components/ForecastVsActualChart.jsx";
import ForecastRevisionChart from "./components/ForecastRevisionChart.jsx";
import ForecastValueComparison from "./components/ForecastValueComparison.jsx";
import MetricsCards from "./components/MetricsCards.jsx";
import RampEventsPanel from "./components/RampEventsPanel.jsx";
import UncertaintyForecastChart from "./components/UncertaintyForecastChart.jsx";
import WindRegimeChart from "./components/WindRegimeChart.jsx";

const INITIAL_FILTERS = {
  start: "2026-01-02",
  end: "2026-02-01",
  delivery_date: "2026-01-31",
  cutoff_hour: 9,
  cutoff_minute: 0,
};

export default function App() {
  const [theme, setTheme] = useState(
    () => (localStorage.getItem("wind-dashboard-theme") === "light" ? "light" : "dark"),
  );
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState(INITIAL_FILTERS);
  const [config, setConfig] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [latestError, setLatestError] = useState("");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("wind-dashboard-theme", theme);
  }, [theme]);

  useEffect(() => {
    getConfig()
      .then((result) => {
        setConfig(result);
        const latestAvailableDate = result.forecast_coverage?.end
          ? new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/London" }).format(
              new Date(result.forecast_coverage.end),
            )
          : null;
        const latestForecastDate =
          latestAvailableDate && latestAvailableDate > "2026-02-01"
            ? "2026-02-01"
            : latestAvailableDate;
        if (latestForecastDate && latestForecastDate !== filters.delivery_date) {
          setFilters((current) => ({ ...current, delivery_date: latestForecastDate }));
          setAppliedFilters((current) => ({
            ...current,
            delivery_date: latestForecastDate,
          }));
        }
      })
      .catch((cause) => setError(`Could not load dashboard configuration: ${cause.message}`));
  }, []);

  const loadData = useCallback(async (selectedFilters) => {
    setLoading(true);
    setError("");
    setLatestError("");
    try {
      const result = await getDashboardData(selectedFilters);
      setData(result);
      setLatestError(result.latestError);
    } catch (cause) {
      setError(cause.message || "Could not load dashboard data.");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(appliedFilters);
  }, [appliedFilters, loadData]);

  function submit(event) {
    event.preventDefault();
    if (filters.start > filters.end) {
      setError("The start date must be on or before the end date.");
      return;
    }
    setAppliedFilters({ ...filters });
  }

  const rangeLabel =
    config?.start_date && config?.end_date
      ? `${config.start_date} to ${config.end_date}`
      : "2 January to 1 February 2026";

  return (
    <main className="page-shell">
      <header className="page-header">
        <div className="brand-mark" aria-hidden="true">W</div>
        <div>
          <p className="eyebrow">GB wind · day-ahead monitoring</p>
          <h1>Wind Forecast Monitor</h1>
          <p className="header-summary">
            Historical accuracy for forecasts available at the trading decision cutoff.
          </p>
        </div>
        <div className="header-actions">
          <span className="coverage-pill">Coverage: {rangeLabel}</span>
          <button
            className="theme-toggle"
            type="button"
            onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? "☀ Light mode" : "☾ Dark mode"}
          </button>
        </div>
      </header>

      <ControlsBar
        value={filters}
        onChange={setFilters}
        onSubmit={submit}
        disabled={loading}
      />

      {error && (
        <div className="error-banner" role="alert">
          <strong>Dashboard data unavailable.</strong> {error}
        </div>
      )}

      {loading ? (
        <div className="loading panel" role="status">
          <span className="spinner" aria-hidden="true" />
          Loading forecast analysis…
        </div>
      ) : data ? (
        <>
          <MetricsCards metrics={data.metrics} />
          <ForecastValueComparison
            baseline={data.naiveBaseline}
            correction={data.biasCorrection}
          />
          <ForecastVsActualChart data={data.forecastVsActual} />
          <UncertaintyForecastChart forecast={data.latestForecast} />
          <BufferCalculator forecast={data.latestForecast} />
          <div className="chart-grid">
            <ErrorByHorizonChart data={data.errorByHorizon} />
            <ErrorByHourChart data={data.errorByHour} />
          </div>
          <CutoffSensitivityChart data={data.cutoffSensitivity} />
          <div className="chart-grid">
            <WindRegimeChart data={data.errorByRegime} />
            <RampEventsPanel data={data.rampEvents} />
          </div>
          <ErrorHeatmap
            data={data.errorHeatmap}
            start={appliedFilters.start}
            end={appliedFilters.end}
          />
          <ForecastRevisionChart
            tracker={data.revisions}
            error={data.revisionsError}
          />
          <div className="chart-grid lower-charts">
            <ErrorHistogram data={data.errorHistogram} />
            <section className="panel level-panel">
              <div className="section-heading">
                <div>
                  <h2>Error by actual output level</h2>
                  <p>Mean absolute error and bias across actual generation quantiles.</p>
                </div>
              </div>
              {data.errorByLevel.length ? (
                <div className="level-table-wrap">
                  <table>
                    <thead>
                      <tr><th scope="col">Actual level (MW)</th><th scope="col">MAE</th><th scope="col">Bias</th><th scope="col">n</th></tr>
                    </thead>
                    <tbody>
                      {data.errorByLevel.map((row) => (
                        <tr key={row.actual_level}>
                          <td>{row.actual_level}</td>
                          <td>{Number(row.mae).toLocaleString(undefined, { maximumFractionDigits: 1 })} MW</td>
                          <td>{Number(row.bias).toLocaleString(undefined, { maximumFractionDigits: 1 })} MW</td>
                          <td>{row.n.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="empty-state">No actual output level data is available.</p>
              )}
            </section>
          </div>
          <BuyingGuidance
            metrics={data.metrics}
            latestForecast={data.latestForecast}
            error={latestError}
          />
        </>
      ) : (
        <section className="panel empty-dashboard">
          <h2>Analysis could not be loaded</h2>
          <p>Check that the API is running, then retry your filters.</p>
          <button className="secondary-button" onClick={() => loadData(appliedFilters)}>
            Try again
          </button>
        </section>
      )}
      <footer className="page-footer">
        Historical analysis only · Forecast error is forecast minus actual · Times shown in London where noted
      </footer>
    </main>
  );
}
