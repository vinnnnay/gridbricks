import { useMemo } from "react";

function heatColor(value, max) {
  if (value == null || !Number.isFinite(Number(value))) return "var(--heat-empty)";
  const ratio = max > 0 ? Math.min(Number(value) / max, 1) : 0;
  const lightness = 95 - ratio * 46;
  return `hsl(190 48% ${lightness}%)`;
}

export default function ErrorHeatmap({ data, start, end }) {
  const dates = useMemo(() => {
    const values = [];
    const current = new Date(`${start}T00:00:00Z`);
    const last = new Date(`${end}T00:00:00Z`);
    while (current <= last) {
      values.push(current.toISOString().slice(0, 10));
      current.setUTCDate(current.getUTCDate() + 1);
    }
    return values;
  }, [start, end]);
  const byCell = new Map(data.map((row) => [`${row.delivery_date}-${row.hour}`, row]));
  const maxMae = Math.max(0, ...data.map((row) => Number(row.mae) || 0));

  return (
    <section className="panel heatmap-panel">
      <div className="section-heading">
        <div>
          <h2>Day × hour forecast error</h2>
          <p>Cell color represents MAE (MW); hover or focus a cell for MAE, bias, and sample count.</p>
        </div>
        <div className="heat-legend" aria-label="Heatmap colors from lower to higher MAE">
          <span>Lower</span><i style={{ background: heatColor(maxMae * 0.15, maxMae) }} />
          <i style={{ background: heatColor(maxMae * 0.5, maxMae) }} />
          <i style={{ background: heatColor(maxMae, maxMae) }} /><span>Higher</span>
        </div>
      </div>
      {data.length ? (
        <div className="heatmap-scroll" role="region" aria-label="Forecast error heatmap" tabIndex={0}>
          <div className="heatmap-grid" style={{ "--day-count": dates.length }}>
            <div className="heatmap-corner" />
            {Array.from({ length: 24 }, (_, hour) => (
              <div className="heatmap-hour" key={`hour-${hour}`}>
                {hour % 3 === 0 ? String(hour).padStart(2, "0") : ""}
              </div>
            ))}
            {dates.flatMap((deliveryDate) => [
              <div className="heatmap-date" key={`date-${deliveryDate}`}>{deliveryDate.slice(8)}</div>,
              ...Array.from({ length: 24 }, (_, hour) => {
                const row = byCell.get(`${deliveryDate}-${hour}`);
                const title = row
                  ? `${deliveryDate} ${String(hour).padStart(2, "0")}:00 London · MAE ${Number(row.mae).toFixed(1)} MW · bias ${Number(row.bias).toFixed(1)} MW · n=${row.n}`
                  : `${deliveryDate} ${String(hour).padStart(2, "0")}:00 London · no matched data`;
                return (
                  <div
                    className="heatmap-cell"
                    key={`${deliveryDate}-${hour}`}
                    style={{ background: heatColor(row?.mae, maxMae) }}
                    title={title}
                    aria-label={title}
                    tabIndex={0}
                  />
                );
              }),
            ])}
          </div>
        </div>
      ) : (
        <p className="empty-state">No day/hour observations are available.</p>
      )}
    </section>
  );
}
