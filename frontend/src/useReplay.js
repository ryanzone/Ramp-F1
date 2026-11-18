import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { replayApi } from "./api.js";
import {
  applyEvents, emptyStore, fromSnapshot, lapRows, pitRows, raceControlRows, stintRows, weatherRows,
} from "./replayModel.js";

const initial = {
  replayId: null,
  status: "idle", // idle | starting | live
  error: null,
  server: null, // last state message from the backend
  serverAt: 0, // performance.now() when it arrived, to extrapolate the clock smoothly
  store: emptyStore(),
  drivers: [],
  connected: false,
};

function reducer(state, action) {
  switch (action.type) {
    case "starting":
      return { ...initial, status: "starting" };
    case "started":
      return { ...state, replayId: action.replayId, status: "live", error: null, server: action.state, serverAt: action.at };
    case "failed":
      return { ...state, status: state.replayId ? state.status : "idle", error: action.message };
    case "stopped":
      return initial;
    case "connected":
      return { ...state, connected: action.value };
    case "reset":
      return {
        ...state, server: action.state, serverAt: action.at, drivers: action.drivers,
        store: fromSnapshot(action.events), error: null,
      };
    case "events":
      // Events carry the epoch they belong to; anything from before a seek is dropped.
      if (state.server && action.epoch !== state.server.epoch) return state;
      return { ...state, store: applyEvents(state.store, action.events) };
    case "state":
      return { ...state, server: action.state, serverAt: action.at };
    default:
      return state;
  }
}

export function useReplay() {
  const [state, dispatch] = useReducer(reducer, initial);
  const { replayId } = state;
  const idRef = useRef(null);

  useEffect(() => {
    idRef.current = replayId;
  }, [replayId]);

  // One WebSocket per replay; the server sends a full snapshot on every (re)connect.
  useEffect(() => {
    if (!replayId) return undefined;
    let closed = false;
    let socket = null;
    let retry = null;
    let failures = 0; // consecutive failed attempts, for exponential backoff (1s, 2s, 4s ... 15s)
    const open = () => {
      socket = new WebSocket(replayApi.wsUrl(replayId));
      socket.onopen = () => {
        failures = 0;
        dispatch({ type: "connected", value: true });
      };
      socket.onmessage = (event) => {
        const m = JSON.parse(event.data);
        const at = performance.now();
        if (m.type === "reset") dispatch({ type: "reset", state: m.state, events: m.events, drivers: m.drivers, at });
        else if (m.type === "events") dispatch({ type: "events", epoch: m.epoch, events: m.events });
        else if (m.type === "state") dispatch({ type: "state", state: m.state, at });
        else if (m.type === "error") dispatch({ type: "failed", message: m.message });
      };
      socket.onclose = () => {
        dispatch({ type: "connected", value: false });
        if (closed) return;
        // Before retrying, make sure the replay still exists (the server was restarted or purged it);
        // a rejected handshake looks like any other drop to the browser, so ask over HTTP.
        retry = setTimeout(async () => {
          try {
            await replayApi.state(replayId);
          } catch (err) {
            if (err.status === 404) {
              closed = true;
              dispatch({ type: "failed", message: "This replay no longer exists on the server. Press Stop and start it again." });
              return;
            }
          }
          if (!closed) open();
        }, Math.min(15000, 1000 * 2 ** failures++));
      };
    };
    open();
    return () => {
      closed = true;
      clearTimeout(retry);
      if (socket) socket.close();
    };
  }, [replayId]);

  // Leaving the page frees the server-side replay.
  useEffect(
    () => () => {
      if (idRef.current) replayApi.stop(idRef.current).catch(() => {});
    },
    [],
  );

  const start = useCallback(async (sessionId, autoplay = false) => {
    dispatch({ type: "starting" });
    try {
      const { replay_id: id, state: s } = await replayApi.start(sessionId);
      dispatch({ type: "started", replayId: id, state: s, at: performance.now() });
      if (autoplay) {
        const playing = await replayApi.play(id);
        dispatch({ type: "state", state: playing, at: performance.now() });
      }
    } catch (err) {
      dispatch({ type: "failed", message: err.message });
    }
  }, []);

  const stop = useCallback(() => {
    const id = idRef.current;
    dispatch({ type: "stopped" });
    if (id) replayApi.stop(id).catch(() => {});
  }, []);

  const control = useCallback(
    async (call) => {
      if (!replayId) return;
      try {
        const next = await call(replayId);
        dispatch({ type: "state", state: next, at: performance.now() });
      } catch (err) {
        dispatch({ type: "failed", message: err.message });
      }
    },
    [replayId],
  );

  const actions = useMemo(
    () => ({
      play: () => control(replayApi.play),
      pause: () => control(replayApi.pause),
      reset: () => control(replayApi.reset),
      setSpeed: (speed) => control((id) => replayApi.speed(id, speed)),
      seek: (offsetSeconds) => control((id) => replayApi.seek(id, offsetSeconds)),
    }),
    [control],
  );

  const byNumber = useMemo(() => Object.fromEntries(state.drivers.map((d) => [d.driver_number, d])), [state.drivers]);

  // Row shapes the existing dashboard panels already understand, built from released events only.
  const rows = useMemo(
    () => ({
      laps: lapRows(state.store, byNumber),
      pits: pitRows(state.store, byNumber),
      stints: stintRows(state.store, byNumber),
      raceControl: raceControlRows(state.store, byNumber),
      weather: weatherRows(state.store),
    }),
    [state.store, byNumber],
  );

  return { ...state, active: state.status === "live", byNumber, rows, start, stop, ...actions };
}
