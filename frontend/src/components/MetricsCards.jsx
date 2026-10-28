const CARDS = [
  { key: "mae", label: "Mean absolute error", unit: "MW", hint: "Average size of the forecast miss." },
  { key: "rmse", label: "Root mean squared error", unit: "MW", hint: "Penalizes larger forecast misses more heavily." },
  { key: "bias", label: "Forecast bias", unit: "MW", hint: "Positive means over-forecasting; negative means under-forecasting." },
  { key: "p90", label: "P90 absolute error", unit: "MW", hint: "90% of absolute misses are at or below this value." },
  { key: "p99", label: "P99 absolute error", unit: "MW", hint: "99% of absolute misses are at or below this value." },
  { key: "n", label: "Matched half-hours", unit: "", hint: "Targets with both an eligible decision forecast and actual." },
];

function formatValue(value) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return Number(value).toLocaleString(undefined, {
    maximumFractionDigits: 1,
  });
}

export default function MetricsCards({ metrics }) {
  return (
    <section className="metrics-grid" aria-label="Forecast accuracy metrics">
      {CARDS.map(({ key, label, unit, hint }) => (
        <article className="metric-card panel" key={key} title={hint}>
          <p className="metric-label">{label}</p>
          <p className="metric-value">
            {formatValue(metrics?.[key])}
            {unit && <span className="metric-unit"> {unit}</span>}
          </p>
          <p className="metric-hint">{hint}</p>
        </article>
      ))}
    </section>
  );
}
