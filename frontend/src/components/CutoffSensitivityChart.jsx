import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function CutoffSensitivityChart({ data }) {
  return (
    <section className="panel chart-panel">
      <div className="section-heading">
        <div>
          <h2>Does a later cutoff improve accuracy?</h2>
          <p>MAE for forecasts selected at each London cutoff, from 06:00 to 12:00.</p>
        </div>
      </div>
      {data.length ? (
        <>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 12, right: 18, left: 0, bottom: 8 }}>
                <CartesianGrid stroke="#e8edf2" strokeDasharray="3 3" />
                <XAxis
                  dataKey="cutoff"
                  tick={{ fill: "#617080", fontSize: 11 }}
                />
                <YAxis width={65} tick={{ fill: "#617080", fontSize: 11 }} />
                <Tooltip
                  formatter={(value, name, item) => [
                    value == null ? "Unavailable" : `${Number(value).toLocaleString()} MW`,
                    `MAE · n=${item.payload.n}`,
                  ]}
                />
                <Line
                  name="MAE"
                  dataKey="mae"
                  stroke="#167d91"
                  strokeWidth={2.5}
                  connectNulls={false}
                  activeDot={{ r: 5 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="method-note">
            Each point uses only forecasts published by that cutoff; sample size is
            shown in the tooltip. A later cutoff is more accurate only if its MAE is lower.
          </p>
        </>
      ) : (
        <p className="empty-state">Cutoff sensitivity data is unavailable.</p>
      )}
    </section>
  );
}
