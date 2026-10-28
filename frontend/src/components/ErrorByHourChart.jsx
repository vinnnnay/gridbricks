import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function ErrorByHourChart({ data }) {
  return (
    <section className="panel chart-panel">
      <div className="section-heading">
        <div>
          <h2>Bias by delivery hour</h2>
          <p>Positive values indicate over-forecasting; times are Europe/London.</p>
        </div>
      </div>
      {data.length ? (
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 8 }}>
              <CartesianGrid stroke="#e8edf2" strokeDasharray="3 3" />
              <XAxis
                dataKey="hour"
                tickFormatter={(hour) => `${String(hour).padStart(2, "0")}:00`}
                tick={{ fill: "#617080", fontSize: 11 }}
              />
              <YAxis width={64} tick={{ fill: "#617080", fontSize: 11 }} />
              <ReferenceLine y={0} stroke="#758494" />
              <Tooltip
                labelFormatter={(hour) => `${String(hour).padStart(2, "0")}:00 London`}
                formatter={(value) => [`${Number(value).toLocaleString()} MW`, "Bias"]}
              />
              <Bar dataKey="bias" name="Bias" fill="#c07119" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="empty-state">No hourly error data is available for this range.</p>
      )}
    </section>
  );
}
