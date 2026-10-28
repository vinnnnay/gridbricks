const API_BASE_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

async function get(path, params = {}) {
  const query = new URLSearchParams(
    Object.entries(params).map(([key, value]) => [key, String(value)]),
  );
  const response = await fetch(`${API_BASE_URL}/api/${path}?${query}`);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // Keep the HTTP status message when the server does not return JSON.
    }
    throw new Error(detail);
  }
  return response.json();
}

export function getConfig() {
  return get("config");
}

export function getDashboardData({
  start,
  end,
  delivery_date,
  cutoff_hour,
  cutoff_minute,
}) {
  const params = { start, end, cutoff_hour, cutoff_minute };
  const dashboardRequests = Promise.all([
    get("forecast-vs-actual", params),
    get("metrics", params),
    get("error-by-horizon", params),
    get("error-by-hour", params),
    get("error-by-level", params),
    get("error-histogram", params),
    get("cutoff-sensitivity", {
      start,
      end,
      cutoff_minute,
    }),
    get("naive-baseline", params),
    get("bias-correction", params),
    get("ramp-events", params),
    get("error-by-regime", params),
    get("error-heatmap", params),
  ]);
  const latestRequest = get("latest-forecast", {
    delivery_date,
    cutoff_hour,
    cutoff_minute,
  }).then(
    (latestForecast) => ({ latestForecast, latestError: "" }),
    (error) => ({ latestForecast: null, latestError: error.message }),
  );
  const revisionsRequest = get("forecast-revisions", { delivery_date }).then(
    (revisions) => ({ revisions, revisionsError: "" }),
    (error) => ({ revisions: null, revisionsError: error.message }),
  );
  return Promise.all([dashboardRequests, latestRequest, revisionsRequest]).then(
    ([[
      forecastVsActual,
      metrics,
      errorByHorizon,
      errorByHour,
      errorByLevel,
      errorHistogram,
      cutoffSensitivity,
      naiveBaseline,
      biasCorrection,
      rampEvents,
      errorByRegime,
      errorHeatmap,
    ], latest, revisionResult]) => ({
      forecastVsActual,
      metrics,
      errorByHorizon,
      errorByHour,
      errorByLevel,
      errorHistogram,
      cutoffSensitivity,
      naiveBaseline,
      biasCorrection,
      rampEvents,
      errorByRegime,
      errorHeatmap,
      latestForecast: latest.latestForecast,
      latestError: latest.latestError,
      revisions: revisionResult.revisions,
      revisionsError: revisionResult.revisionsError,
    }),
  );
}
