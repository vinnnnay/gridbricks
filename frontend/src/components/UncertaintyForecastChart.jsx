import {
  Area,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function slotLabel(value) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export default function UncertaintyForecastChart({ forecast }) {
  const rows = forecast?.rows || [];
  const coverage = forecast?.coverage;
  const coverageText =
    coverage?.coverage == null
      ? "Coverage check unavailable"
      : `${(coverage.coverage * 100).toFixed(1)}% of ${coverage.total.toLocaleString()} held-out historical points fell inside the P10–P90 band (nominal target: 80%).`;

  return (
    <section className="panel chart-panel">
      <div className="section-heading">
        <div>
          <h2>Latest eligible forecast with uncertainty</h2>
          <p>
            Expected wind output and a conditional P10–P90 range based on prior
            forecast errors at similar horizons and output levels.
          </p>
        </div>
        {forecast && <span className="coverage-pill">{forecast.delivery_date}</span>}
      </div>
      {rows.length ? (
        <>
          <div className="chart-wrap">
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
                    value == null ? "Unavailable" : `${Number(value).toLocaleString()} MW`,
                    name,
                  ]}
                />
                <Legend />
                <Area
                  dataKey="p10"
                  stackId="uncertainty"
                  stroke="none"
                  fill="transparent"
                  connectNulls
                  legendType="none"
                />
                <Area
                  dataKey={(row) =>
                    row.p10 == null || row.p90 == null ? null : Math.max(0, row.p90 - row.p10)
                  }
                  name="P10–P90 plausible range"
                  stackId="uncertainty"
                  stroke="none"
                  fill="#8bcbd3"
                  fillOpacity={0.42}
                  connectNulls
                />
                <Line
                  name="Forecast"
                  dataKey="forecast"
                  stroke="#126f82"
                  strokeWidth={2.5}
                  dot={false}
                />
                <Line
                  name="P10 lower bound"
                  dataKey="p10"
                  stroke="#477f89"
                  strokeDasharray="4 4"
                  strokeWidth={1}
                  dot={false}
                  connectNulls
                />
                <Line
                  name="P90 upper bound"
                  dataKey="p90"
                  stroke="#477f89"
                  strokeDasharray="4 4"
                  strokeWidth={1}
                  dot={false}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="coverage-note" role="status">{coverageText}</p>
          <p className="method-note">
            Calibration excludes the selected delivery day. Sparse horizon/output
            buckets fall back to broader historical groups; the source and sample
            count are included for each half-hour.
          </p>
        </>
      ) : (
        <p className="empty-state">No eligible forecast is available for this delivery date.</p>
      )}
    </section>
  );
}
