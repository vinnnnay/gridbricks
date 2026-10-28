import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function WindRegimeChart({ data }) {
  return (
    <section className="panel chart-panel">
      <div className="section-heading">
        <div>
          <h2>Error by wind regime</h2>
          <p>Low, medium, and high bands are based on terciles of actual wind in this selection.</p>
        </div>
      </div>
      {data.length ? (
        <>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 8 }}>
                <CartesianGrid stroke="#e8edf2" strokeDasharray="3 3" />
                <XAxis dataKey="regime" tick={{ fill: "#617080", fontSize: 12 }} />
                <YAxis width={64} tick={{ fill: "#617080", fontSize: 11 }} />
                <Tooltip
                  formatter={(value, name) => [`${Number(value).toLocaleString()} MW`, name]}
                  labelFormatter={(label, payload) => {
                    const row = payload?.[0]?.payload;
                    return row
                      ? `${label}: ${Number(row.actual_min).toLocaleString()}–${Number(row.actual_max).toLocaleString()} MW actual · n=${row.n}`
                      : label;
                  }}
                />
                <Bar dataKey="mae" name="MAE" fill="#167d91" radius={[4, 4, 0, 0]} />
                <Bar dataKey="bias" name="Bias" fill="#c07119" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="method-note">Regime cut-points are calculated from the selected period, not fixed MW thresholds.</p>
        </>
      ) : (
        <p className="empty-state">No wind-regime data is available.</p>
      )}
    </section>
  );
}
