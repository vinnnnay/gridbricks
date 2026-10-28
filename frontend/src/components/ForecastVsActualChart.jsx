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

function timeLabel(value) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export default function ForecastVsActualChart({ data }) {
  return (
    <section className="panel chart-panel">
      <div className="section-heading">
        <div>
          <h2>Forecast vs actual</h2>
          <p>Selected day-ahead forecast compared with delivered wind generation.</p>
        </div>
      </div>
      {data.length ? (
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 8 }}>
              <CartesianGrid stroke="#e8edf2" strokeDasharray="3 3" />
              <XAxis
                dataKey="startTime"
                tickFormatter={timeLabel}
                minTickGap={32}
                tick={{ fill: "#617080", fontSize: 11 }}
              />
              <YAxis
                width={64}
                tick={{ fill: "#617080", fontSize: 11 }}
                tickFormatter={(value) => `${Number(value).toLocaleString()} MW`}
              />
              <Tooltip
                labelFormatter={timeLabel}
                formatter={(value, name) => [`${Number(value).toLocaleString()} MW`, name]}
              />
              <Legend />
              <Line
                name="Forecast"
                dataKey="forecast"
                stroke="#167d91"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
              <Line
                name="Actual"
                dataKey="actual"
                stroke="#c07119"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="empty-state">No matched forecast and actual data for this range.</p>
      )}
    </section>
  );
}
