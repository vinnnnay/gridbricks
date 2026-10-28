import { useMemo, useState } from "react";

function slotLabel(value) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function BufferCalculator({ forecast }) {
  const rows = forecast?.rows || [];
  const [demand, setDemand] = useState("");
  const [slot, setSlot] = useState("");
  const selectedSlot = useMemo(
    () => rows.find((row) => row.startTime === (slot || rows[0]?.startTime)),
    [rows, slot],
  );
  const demandValue = demand === "" ? null : Number(demand);
  const hasInput = Number.isFinite(demandValue) && demandValue >= 0;
  const hasBand =
    selectedSlot &&
    Number.isFinite(selectedSlot.forecast) &&
    Number.isFinite(selectedSlot.p10);
  const expectedGap = hasInput && selectedSlot
    ? Math.max(0, demandValue - selectedSlot.forecast)
    : null;
  const riskAdjustedThermal = hasInput && hasBand
    ? Math.max(0, demandValue - selectedSlot.p10)
    : null;

  return (
    <section className="panel calculator-panel">
      <div className="section-heading">
        <div>
          <h2>Thermal buffer calculator</h2>
          <p>Enter expected demand and choose a delivery half-hour. Demand is your input.</p>
        </div>
      </div>
      {rows.length ? (
        <>
          <div className="calculator-controls">
            <label>
              Expected demand (MW)
              <input
                type="number"
                min="0"
                step="any"
                value={demand}
                onChange={(event) => setDemand(event.target.value)}
                placeholder="e.g. 30000"
              />
            </label>
            <label>
              Delivery half-hour (London)
              <select value={selectedSlot?.startTime || ""} onChange={(event) => setSlot(event.target.value)}>
                {rows.map((row) => (
                  <option value={row.startTime} key={row.startTime}>
                    {slotLabel(row.startTime)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {selectedSlot && hasInput ? (
            <div className="buffer-results">
              <div>
                <span>Gap after expected wind</span>
                <strong>{expectedGap.toLocaleString(undefined, { maximumFractionDigits: 1 })} MW</strong>
                <small>Demand minus the forecast ({selectedSlot.forecast.toLocaleString()} MW).</small>
              </div>
              <div className="risk-result">
                <span>90% risk-adjusted thermal cover</span>
                <strong>
                  {riskAdjustedThermal == null
                    ? "Unavailable"
                    : `${riskAdjustedThermal.toLocaleString(undefined, { maximumFractionDigits: 1 })} MW`}
                </strong>
                <small>
                  {hasBand
                    ? `At least this much covers demand if wind lands at its P10 lower bound (${selectedSlot.p10.toLocaleString(undefined, { maximumFractionDigits: 1 })} MW).`
                    : "A calibrated P10 wind estimate is unavailable for this half-hour."}
                </small>
              </div>
            </div>
          ) : (
            <p className="method-note">Enter a non-negative demand value to calculate the indicative thermal cover.</p>
          )}
        </>
      ) : (
        <p className="empty-state">A forecast is needed before calculating a wind-adjusted buffer.</p>
      )}
      <p className="method-note">
        Indicative historical planning aid only; this does not account for outages,
        reserves, market rules, or other generation sources.
      </p>
    </section>
  );
}
