function formatMw(value) {
  return value == null || !Number.isFinite(Number(value))
    ? "Unavailable"
    : `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })} MW`;
}

function formatPercent(value) {
  return value == null || !Number.isFinite(Number(value))
    ? "Unavailable"
    : `${(Number(value) * 100).toFixed(1)}%`;
}

export default function ForecastValueComparison({ baseline, correction }) {
  return (
    <div className="chart-grid value-comparison">
      <section className="panel value-card">
        <p className="eyebrow">Naive baseline</p>
        <h2>Does the forecast add value?</h2>
        <p className="value-hero">{formatPercent(baseline?.skill_score)}</p>
        <p>
          Skill score = 1 − forecast MAE / yesterday-actual MAE. Positive means the
          forecast beat using the same half-hour yesterday.
        </p>
        <dl className="comparison-stats">
          <div><dt>Forecast MAE</dt><dd>{formatMw(baseline?.mae_forecast)}</dd></div>
          <div><dt>Yesterday baseline MAE</dt><dd>{formatMw(baseline?.mae_baseline)}</dd></div>
          <div><dt>Matched half-hours</dt><dd>{baseline?.n?.toLocaleString() ?? "0"}</dd></div>
        </dl>
      </section>
      <section className="panel value-card">
        <p className="eyebrow">Walk-forward bias correction</p>
        <h2>Past-hour bias adjustment</h2>
        <p className="value-hero">{formatMw(correction?.mae_improvement)}</p>
        <p>
          MAE improvement after subtracting the mean forecast bias for that London
          hour, trained only on earlier delivery days.
        </p>
        <dl className="comparison-stats">
          <div><dt>Raw MAE</dt><dd>{formatMw(correction?.mae_forecast)}</dd></div>
          <div><dt>Corrected MAE</dt><dd>{formatMw(correction?.mae_corrected)}</dd></div>
          <div><dt>Relative improvement</dt><dd>{formatPercent(correction?.mae_improvement_share)}</dd></div>
          <div><dt>Walk-forward samples</dt><dd>{correction?.n?.toLocaleString() ?? "0"}</dd></div>
        </dl>
      </section>
    </div>
  );
}
