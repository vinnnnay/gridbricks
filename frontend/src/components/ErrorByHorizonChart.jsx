import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function ErrorByHorizonChart({ data }) {
  return (
    <section className="panel chart-panel">
      <div className="section-heading">
        <div>
          <h2>Error by forecast horizon</h2>
          <p>Mean absolute error across all available forecasts, grouped by lead time.</p>
        </div>
      </div>
      {data.length ? (
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 8 }}>
              <CartesianGrid stroke="#e8edf2" strokeDasharray="3 3" />
              <XAxis dataKey="horizon" tick={{ fill: "#617080", fontSize: 11 }} />
              <YAxis width={64} tick={{ fill: "#617080", fontSize: 11 }} />
              <Tooltip formatter={(value) => [`${Number(value).toLocaleString()} MW`, "MAE"]} />
              <Bar dataKey="mae" name="MAE" fill="#167d91" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="empty-state">No forecast horizon data is available for this range.</p>
      )}
    </section>
  );
}
