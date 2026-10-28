const MIN_DATE = "2026-01-02";
const MAX_DATE = "2026-02-01";

export default function ControlsBar({ value, onChange, onSubmit, disabled }) {
  function update(key, nextValue) {
    onChange({ ...value, [key]: nextValue });
  }

  return (
    <form className="controls panel" onSubmit={onSubmit}>
      <div className="control-field">
        <label htmlFor="start-date">Delivery from</label>
        <input
          id="start-date"
          type="date"
          min={MIN_DATE}
          max={MAX_DATE}
          value={value.start}
          onChange={(event) => update("start", event.target.value)}
          required
        />
      </div>
      <div className="control-field">
        <label htmlFor="end-date">Delivery to</label>
        <input
          id="end-date"
          type="date"
          min={MIN_DATE}
          max={MAX_DATE}
          value={value.end}
          onChange={(event) => update("end", event.target.value)}
          required
        />
      </div>
      <div className="control-field">
        <label htmlFor="focus-delivery-date">Featured delivery day</label>
        <input
          id="focus-delivery-date"
          type="date"
          min={MIN_DATE}
          max={MAX_DATE}
          value={value.delivery_date}
          onChange={(event) => update("delivery_date", event.target.value)}
          required
        />
      </div>
      <div className="control-field cutoff-field">
        <label htmlFor="cutoff-time">Decision cutoff (London)</label>
        <input
          id="cutoff-time"
          type="time"
          value={`${String(value.cutoff_hour).padStart(2, "0")}:${String(
            value.cutoff_minute,
          ).padStart(2, "0")}`}
          onChange={(event) => {
            const [hour, minute] = event.target.value.split(":").map(Number);
            onChange({ ...value, cutoff_hour: hour, cutoff_minute: minute });
          }}
          required
        />
      </div>
      <button className="primary-button" type="submit" disabled={disabled}>
        Apply filters
      </button>
      <p className="controls-note">
        Showing forecasts as they stood at {String(value.cutoff_hour).padStart(2, "0")}:
        {String(value.cutoff_minute).padStart(2, "0")} on the day before delivery.
      </p>
    </form>
  );
}
