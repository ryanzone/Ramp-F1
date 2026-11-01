const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request(path, params) {
  const url = new URL(`${API_BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.append(key, String(value));
      }
    });
  }
  const res = await fetch(url.toString());
  if (!res.ok) {
    throw new Error(`API ${path} failed (${res.status})`);
  }
  return res.json();
}

export const api = {
  health: () => request("/api/health"),
  races: () => request("/api/races"),
  drivers: (sessionId) => request("/api/drivers", { session_id: sessionId }),
  laps: (driverCode, sessionId) =>
    request("/api/laps", { driver_code: driverCode, session_id: sessionId }),
  pitStops: (sessionId) => request("/api/pit-stops", { session_id: sessionId }),
  tyreStints: (sessionId) =>
    request("/api/tyre-stints", { session_id: sessionId }),
  weather: (sessionId) => request("/api/weather", { session_id: sessionId }),
  raceControl: (sessionId) =>
    request("/api/race-control", { session_id: sessionId }),
};

export { API_BASE };
