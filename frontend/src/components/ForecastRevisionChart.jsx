import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const REVISION_COLORS = ["#7188a5", "#9d7bb5", "#db9860", "#4c9c8b", "#9a9e57", "#bf7183"];

function slotLabel(value) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function chartRows(tracker) {
  const rowsByTime = new Map();
  for (const point of tracker?.actuals || []) {
    rowsByTime.set(point.startTime, { startTime: point.startTime, actual: point.actual });
  }
  for (const [revisionIndex, revision] of (tracker?.revisions || []).entries()) {
    for (const point of revision.rows) {
      const current = rowsByTime.get(point.startTime) || { startTime: point.startTime };
      current[`revision_${revisionIndex}`] = point.forecast;
      rowsByTime.set(point.startTime, current);
    }
  }
  return [...rowsByTime.values()].sort(
    (left, right) => new Date(left.startTime) - new Date(right.startTime),
  );
}

export default function ForecastRevisionChart({ tracker, error }) {
  const rows = chartRows(tracker);
  const revisions = tracker?.revisions || [];
  return (
    <section className="panel chart-panel">
      <div className="section-heading">
        <div>
          <h2>Forecast revision tracker</h2>
          <p>Every published forecast version for the selected delivery date, compared with actual wind.</p>
        </div>
        {tracker && (
          <span className="coverage-pill">
            {tracker.revision_count} published versions
          </span>
        )}
      </div>
      {error ? (
        <p className="empty-state">{error}</p>
      ) : rows.length ? (
        <>
          <div className="chart-wrap revision-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 12, right: 12, left: 0, bottom: 8 }}>
                <CartesianGrid stroke="#e8edf2" strokeDasharray="3 3" />
                <XAxis
                  dataKey="startTime"
                  tickFormatter={slotLabel}
                  minTickGap={24}
                  tick={{ fill: "#617080", fontSize: 11 }}
                />
                <YAxis width={72} tick={{ fill: "#617080", fontSize: 11 }} />
                <Tooltip
                  labelFormatter={(value) => `${slotLabel(value)} London`}
                  formatter={(value, name) => [
                    `${Number(value).toLocaleString()} MW`,
                    name,
                  ]}
                />
                <Legend />
                {revisions.map((revision, index) => (
                  <Line
                    key={revision.publishTime}
                    name={`Published ${new Intl.DateTimeFormat("en-GB", {
                      timeZone: "Europe/London",
                      hour: "2-digit",
                      minute: "2-digit",
                    }).format(new Date(revision.publishTime))}`}
                    dataKey={`revision_${index}`}
                    stroke={REVISION_COLORS[index % REVISION_COLORS.length]}
                    strokeOpacity={0.45}
                    strokeWidth={1}
                    dot={false}
                    activeDot={false}
                    connectNulls
                  />
                ))}
                <Line
                  name="Actual"
                  dataKey="actual"
                  stroke="#172a3a"
                  strokeWidth={2.5}
                  dot={false}
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="method-note">
            Thin lines show each publish time ({revisions.length} total). Revision
            coverage can vary between versions and half-hours.
          </p>
        </>
      ) : (
        <p className="empty-state">No published versions are available for this delivery date.</p>
      )}
    </section>
  );
}
