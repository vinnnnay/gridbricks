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

export default function ErrorHistogram({ data }) {
  const formatted = data.map((bin) => ({
    ...bin,
    midpoint: (bin.bin_start + bin.bin_end) / 2,
    range: `${Math.round(bin.bin_start).toLocaleString()} to ${Math.round(
      bin.bin_end,
    ).toLocaleString()} MW`,
  }));
  return (
    <section className="panel chart-panel">
      <div className="section-heading">
        <div>
          <h2>Forecast error distribution</h2>
          <p>Signed error = forecast minus actual. Positive means over-forecasting.</p>
        </div>
      </div>
      {formatted.length ? (
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={formatted} margin={{ top: 12, right: 12, left: 0, bottom: 8 }}>
              <CartesianGrid stroke="#e8edf2" strokeDasharray="3 3" />
              <XAxis
                dataKey="midpoint"
                type="number"
                domain={["dataMin", "dataMax"]}
                tick={{ fill: "#617080", fontSize: 11 }}
                tickFormatter={(value) => Math.round(value).toLocaleString()}
              />
              <YAxis width={50} tick={{ fill: "#617080", fontSize: 11 }} />
              <ReferenceLine x={0} stroke="#758494" />
              <Tooltip
                labelFormatter={(_, payload) => payload?.[0]?.payload?.range || ""}
                formatter={(value) => [Number(value).toLocaleString(), "Half-hours"]}
              />
              <Bar dataKey="count" name="Half-hours" fill="#5b7596" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="empty-state">No error distribution is available for this range.</p>
      )}
    </section>
  );
}
