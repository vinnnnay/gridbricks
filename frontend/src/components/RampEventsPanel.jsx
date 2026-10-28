function formatMw(value) {
  return value == null || !Number.isFinite(Number(value))
    ? "Unavailable"
    : `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })} MW`;
}

function formatTime(value) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function RampEventsPanel({ data }) {
  const summary = data?.summary;
  const events = data?.events || [];
  return (
    <section className="panel level-panel ramp-panel">
      <div className="section-heading">
        <div>
          <h2>Large 30-minute wind ramps</h2>
          <p>Actual changes at or above the 500 MW threshold, and whether the forecast caught the direction.</p>
        </div>
      </div>
      <div className="ramp-summary">
        <div><span>Ramp events</span><strong>{summary?.event_count ?? 0}</strong></div>
        <div><span>Direction caught</span><strong>{summary?.direction_caught_share == null ? "—" : `${(summary.direction_caught_share * 100).toFixed(1)}%`}</strong></div>
        <div><span>MAE on ramps</span><strong>{formatMw(summary?.mae_on_ramps)}</strong></div>
        <div><span>Threshold</span><strong>{formatMw(summary?.threshold_mw)}</strong></div>
      </div>
      {events.length ? (
        <div className="level-table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Delivery time</th>
                <th scope="col">Actual ramp</th>
                <th scope="col">Forecast ramp</th>
                <th scope="col">Forecast interval</th>
                <th scope="col">Direction caught</th>
                <th scope="col">Forecast error</th>
              </tr>
            </thead>
            <tbody>
              {events.slice(0, 50).map((event) => (
                <tr key={event.startTime}>
                  <td>{formatTime(event.startTime)}</td>
                  <td>{formatMw(event.actual_ramp)}</td>
                  <td>{formatMw(event.forecast_ramp)}</td>
                  <td>{event.forecast_interval_minutes == null ? "Unavailable" : `${event.forecast_interval_minutes} min`}</td>
                  <td>{event.forecast_ramp == null ? "No prior forecast" : event.direction_caught ? "Yes" : "No"}</td>
                  <td>{formatMw(event.forecast_error)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {events.length > 50 && <p className="method-note">Showing the first 50 of {events.length} ramp events.</p>}
        </div>
      ) : (
        <p className="empty-state">No actual wind changes met the ramp threshold in this date range.</p>
      )}
      <p className="method-note">Direction caught means forecast ramp and actual ramp have the same sign. Forecast data can be hourly, so the closest earlier forecast is used (up to 90 minutes before the event); its interval is shown in the table. Change the 500 MW threshold in the API to explore other ramp sizes.</p>
    </section>
  );
}
