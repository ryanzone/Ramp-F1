const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function fail(path, res) {
  let detail = "";
  try {
    const body = await res.json();
    detail = typeof body.detail === "string" ? body.detail : "";
  } catch {
    /* no JSON body */
  }
  const error = new Error(detail || `API ${path} failed (${res.status})`);
  error.status = res.status;
  throw error;
}

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
  if (!res.ok) await fail(path, res);
  return res.json();
}

async function send(method, path, body, params) {
  const url = new URL(`${API_BASE}${path}`);
  Object.entries(params || {}).forEach(([k, v]) => v != null && url.searchParams.append(k, String(v)));
  const res = await fetch(url.toString(), {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) await fail(path, res);
  return res.json();
}

export const api = {
  health: () => request("/api/health"),
  races: () => request("/api/races"),
  drivers: (sessionId) => request("/api/drivers", { session_id: sessionId }),
  results: (sessionId) => request("/api/results", { session_id: sessionId }),
  laps: (driverCode, sessionId) =>
    request("/api/laps", { driver_code: driverCode, session_id: sessionId }),
  pitStops: (sessionId) => request("/api/pit-stops", { session_id: sessionId }),
  tyreStints: (sessionId) =>
    request("/api/tyre-stints", { session_id: sessionId }),
  weather: (sessionId) => request("/api/weather", { session_id: sessionId }),
  raceControl: (sessionId) =>
    request("/api/race-control", { session_id: sessionId }),
};

const wsBase = () => API_BASE.replace(/^http/, "ws");

// Historical replay: a private replay per browser tab, driven by a virtual clock on the server.
export const replayApi = {
  sessions: () => request("/api/replay/sessions"),
  start: (sessionId, speed = 1) => send("POST", "/api/replay/start", { session_id: sessionId, speed }),
  play: (id) => send("POST", "/api/replay/play", undefined, { replay_id: id }),
  pause: (id) => send("POST", "/api/replay/pause", undefined, { replay_id: id }),
  reset: (id) => send("POST", "/api/replay/reset", undefined, { replay_id: id }),
  speed: (id, speed) => send("POST", "/api/replay/speed", { speed }, { replay_id: id }),
  seek: (id, offsetSeconds) =>
    send("POST", "/api/replay/seek", { offset_seconds: offsetSeconds }, { replay_id: id }),
  state: (id) => request("/api/replay/state", { replay_id: id }),
  stop: (id) => send("DELETE", `/api/replay/${id}`),
  postRaceAnalysis: (id) => request("/api/replay/postrace-analysis", { replay_id: id }),
  wsUrl: (id) => `${wsBase()}/ws/replay?replay_id=${encodeURIComponent(id)}`,
};

// Natural-language questions answered by real SQL at the replay clock.
export const analyticsApi = {
  query: (replayId, question, remember = true) =>
    send("POST", "/api/analytics/query", { replay_id: replayId, question, remember }),
  explain: (replayId, queryId) =>
    send("POST", "/api/analytics/explain", { replay_id: replayId, query_id: queryId }),
  history: (replayId) => request("/api/analytics/history", { replay_id: replayId }),
  intents: () => request("/api/analytics/intents"),
  wsUrl: () => `${wsBase()}/ws/analytics`,
};

export { API_BASE };
