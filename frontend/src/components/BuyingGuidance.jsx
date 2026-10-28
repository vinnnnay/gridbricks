export default function BuyingGuidance({ metrics, latestForecast, error }) {
  const p90 = metrics?.p90;
  return (
    <section className="guidance panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Historical insight, not a guarantee</p>
          <h2>Buying guidance</h2>
        </div>
      </div>
      {Number.isFinite(p90) ? (
        <p>
          For the selected period, 90% of day-ahead wind forecast misses were within
          approximately <strong>±{Number(p90).toLocaleString(undefined, { maximumFractionDigits: 1 })} MW</strong>.
          This historical absolute-error range can be used as a symmetric planning
          buffer reference; actual under-delivery risk may differ.
        </p>
      ) : (
        <p>There is not enough matched data in this selection to estimate a historical buffer.</p>
      )}
      {error ? (
        <p className="inline-warning" role="status">{error}</p>
      ) : latestForecast ? (
        <p className="latest-note">
          Latest eligible publish for delivery {latestForecast.delivery_date}:{" "}
          <time dateTime={latestForecast.publishTime}>
            {new Intl.DateTimeFormat("en-GB", {
              timeZone: "Europe/London",
              dateStyle: "medium",
              timeStyle: "short",
            }).format(new Date(latestForecast.publishTime))} London
          </time>
          {" "}({latestForecast.count} half-hours available).
        </p>
      ) : null}
    </section>
  );
}
