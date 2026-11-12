// Pure helpers for the replay UI: fold released events into a store and derive what the
// dashboard shows. Only events at or before the replay clock ever reach this code, so
// nothing here can reveal the future. No React in this file (tested with `node --test`).

export const TEAM_COLORS = {
  mercedes: "#27f4d2",
  ferrari: "#e80020",
  mclaren: "#ff8000",
  "red bull racing": "#3671c6",
  williams: "#64c4ff",
  "aston martin": "#229971",
  alpine: "#ff87bc",
  "racing bulls": "#6692ff",
  "haas f1 team": "#b6babd",
  audi: "#f50537",
  cadillac: "#c9c9c9",
  "kick sauber": "#52e252",
};

const FALLBACK = ["#4788ef", "#ff914d", "#bd7aff", "#ffd166", "#49d7cb", "#56c78b"];

export function teamColor(team) {
  const key = String(team || "").toLowerCase();
  if (TEAM_COLORS[key]) return TEAM_COLORS[key];
  let h = 0;
  for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return FALLBACK[h % FALLBACK.length];
}

export const COMPOUNDS = {
  SOFT: { letter: "S", color: "#ff4d62", label: "Soft" },
  MEDIUM: { letter: "M", color: "#f4cf45", label: "Medium" },
  HARD: { letter: "H", color: "#e8e9ed", label: "Hard" },
  INTERMEDIATE: { letter: "I", color: "#49d7cb", label: "Inter" },
  WET: { letter: "W", color: "#4788ef", label: "Wet" },
};

export function compoundInfo(name) {
  return COMPOUNDS[String(name || "").toUpperCase()] || { letter: "?", color: "#858a97", label: "Unknown" };
}

// ---- store -----------------------------------------------------------------------------
export function emptyStore() {
  return {
    lapsByDriver: {}, // driver_number -> lap_complete events in order
    stintsByDriver: {}, // driver_number -> { stint_number: { start, end } }
    pits: [],
    raceControl: [],
    weather: null,
    positions: {}, // driver_number -> { position, t }
    gaps: {}, // driver_number -> { gap, interval, t }
    lapCount: 0,
  };
}

// Copy-on-write fold: never mutates `prev`, so React can compare by reference.
export function applyEvents(prev, events) {
  if (!events || !events.length) return prev;
  const next = { ...prev };
  const own = new Set();
  const writable = (key) => {
    if (!own.has(key)) {
      next[key] = Array.isArray(prev[key]) ? prev[key].slice() : { ...prev[key] };
      own.add(key);
    }
    return next[key];
  };
  for (const e of events) {
    const n = e.driver_number;
    switch (e.kind) {
      case "lap_complete": {
        const byDriver = writable("lapsByDriver");
        byDriver[n] = (byDriver[n] || []).concat(e);
        next.lapCount = (next.lapCount || 0) + 1;
        break;
      }
      case "stint": {
        const byDriver = writable("stintsByDriver");
        const entry = { ...(byDriver[n] || {}) };
        const slot = { ...(entry[e.data.stint_number] || {}) };
        slot[e.data.phase === "end" ? "end" : "start"] = e;
        entry[e.data.stint_number] = slot;
        byDriver[n] = entry;
        break;
      }
      case "pit_stop":
        writable("pits").push(e);
        break;
      case "race_control":
        writable("raceControl").push(e);
        break;
      case "weather":
        next.weather = !next.weather || e.t >= next.weather.t ? e : next.weather;
        break;
      case "position": {
        const positions = writable("positions");
        if (!positions[n] || e.t >= positions[n].t) positions[n] = { position: e.data.position, t: e.t };
        break;
      }
      case "interval": {
        const gaps = writable("gaps");
        if (!gaps[n] || e.t >= gaps[n].t)
          gaps[n] = { gap: e.data.gap_to_leader, interval: e.data.interval_ahead, t: e.t };
        break;
      }
      default:
        break;
    }
  }
  return next;
}

export function fromSnapshot(events) {
  return applyEvents(emptyStore(), events);
}

// ---- derived views -----------------------------------------------------------------------
export function lastLap(store, number) {
  const laps = store.lapsByDriver[number] || [];
  return laps.length ? laps[laps.length - 1] : null;
}

export function currentStint(store, number) {
  const stints = store.stintsByDriver[number];
  if (!stints) return null;
  const numbers = Object.keys(stints).map(Number).sort((a, b) => a - b);
  for (let i = numbers.length - 1; i >= 0; i--) {
    const slot = stints[numbers[i]];
    if (slot.start) {
      const d = slot.start.data;
      const last = lastLap(store, number);
      const completed = last && last.lap_number >= d.start_lap ? last.lap_number - d.start_lap + 1 : 0;
      return {
        stint_number: d.stint_number,
        compound: d.compound,
        start_lap: d.start_lap,
        laps_completed: completed,
        tyre_age: (d.starting_tyre_age || 0) + completed,
        finished: Boolean(slot.end),
      };
    }
  }
  return null;
}

export function standings(store, drivers) {
  return drivers
    .map((d) => {
      const pos = store.positions[d.driver_number];
      const gap = store.gaps[d.driver_number];
      const ll = lastLap(store, d.driver_number);
      return {
        number: d.driver_number,
        code: d.code,
        name: d.name,
        team: d.team,
        color: teamColor(d.team),
        position: pos ? pos.position : null,
        gap: gap ? gap.gap : null,
        interval: gap ? gap.interval : null,
        stint: currentStint(store, d.driver_number),
        lastLap: ll ? ll.data.lap_duration : null,
        lapsDone: ll ? ll.lap_number : 0,
      };
    })
    .sort((a, b) => (a.position ?? 99) - (b.position ?? 99) || a.code.localeCompare(b.code));
}

// Last completed lap with sector deltas against the driver's own best earlier sectors.
export function sectorBoard(store, number) {
  const laps = store.lapsByDriver[number] || [];
  if (!laps.length) return null;
  const last = laps[laps.length - 1];
  const earlier = laps.slice(0, -1).filter((l) => l.data.is_valid !== false);
  const best = (key) => {
    const vals = earlier.map((l) => l.data[key]).filter((v) => v != null);
    return vals.length ? Math.min(...vals) : null;
  };
  const sector = (key) => {
    const v = last.data[key];
    const b = best(key);
    return { value: v, delta: v != null && b != null ? v - b : null };
  };
  const previous = earlier.length ? earlier[earlier.length - 1].data.lap_duration : null;
  return {
    lap: last.lap_number,
    lapTime: last.data.lap_duration,
    lapDelta: last.data.lap_duration != null && previous != null ? last.data.lap_duration - previous : null,
    speedTrap: last.data.st_speed,
    s1: sector("sector_1"),
    s2: sector("sector_2"),
    s3: sector("sector_3"),
  };
}

export function raceStatus(store) {
  const msgs = store.raceControl;
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = String(msgs[i].data.message || "").toUpperCase();
    const flag = String(msgs[i].data.flag || "").toUpperCase();
    if (m.includes("VSC DEPLOYED")) return { label: "Virtual safety car", tone: "warn" };
    if (m.includes("SAFETY CAR DEPLOYED")) return { label: "Safety car", tone: "warn" };
    if (m.includes("VSC ENDING") || m.includes("SAFETY CAR IN THIS LAP")) return { label: "Restart pending", tone: "warn" };
    if (flag === "RED" || m.includes("RED FLAG")) return { label: "Red flag", tone: "bad" };
    if (flag === "CHEQUERED" || m.includes("CHEQUERED")) return { label: "Finished", tone: "ok" };
    if (flag === "GREEN" || flag === "CLEAR" || m.includes("GREEN LIGHT") || m.includes("TRACK CLEAR")) {
      return { label: "Green flag", tone: "ok" };
    }
  }
  return { label: msgs.length || store.lapCount ? "Racing" : "Awaiting start", tone: "ok" };
}

// ---- adapters: the same row shapes the existing dashboard panels already consume --------
const codeOf = (byNumber, n) => (byNumber[n] ? byNumber[n].code : String(n));

export function lapRows(store, byNumber) {
  const rows = [];
  for (const [n, laps] of Object.entries(store.lapsByDriver)) {
    for (const l of laps) {
      rows.push({
        driver_code: codeOf(byNumber, n),
        lap_number: l.lap_number,
        lap_time_seconds: l.data.lap_duration,
        is_valid: l.data.is_valid,
      });
    }
  }
  return rows;
}

export function pitRows(store, byNumber) {
  return store.pits.map((p) => ({
    driver_code: codeOf(byNumber, p.driver_number),
    lap_number: p.lap_number,
    stop_number: p.data.stop_number,
    stop_duration_seconds: p.data.stop_duration,
    pit_timestamp: p.data.entered_at,
  }));
}

export function stintRows(store, byNumber) {
  const rows = [];
  for (const [n, stints] of Object.entries(store.stintsByDriver)) {
    for (const slot of Object.values(stints)) {
      if (!slot.start) continue;
      const d = slot.start.data;
      const cur = currentStint(store, n);
      const running = !slot.end;
      const lastLapNo = (lastLap(store, n) || {}).lap_number;
      rows.push({
        driver_code: codeOf(byNumber, n),
        stint_number: d.stint_number,
        compound: d.compound,
        start_lap: d.start_lap,
        // A running stint is shown up to the last lap completed; its true end is not known yet.
        end_lap: running ? Math.max(d.start_lap, lastLapNo || d.start_lap) : slot.end.data.end_lap,
        running: running && cur && cur.stint_number === d.stint_number,
      });
    }
  }
  return rows;
}

export function raceControlRows(store, byNumber) {
  return store.raceControl.map((m) => ({
    recorded_at: m.t,
    driver_code: m.driver_number != null ? codeOf(byNumber, m.driver_number) : null,
    lap_number: m.lap_number,
    category: m.data.category,
    message: m.data.message,
  }));
}

export function weatherRows(store) {
  const w = store.weather;
  return w ? [{ recorded_at: w.t, ...w.data }] : [];
}

// ---- time formatting ---------------------------------------------------------------------
export function formatClock(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const pad = (n) => String(n).padStart(2, "0");
  return `${h}:${pad(m)}:${pad(s % 60)}`;
}

export function parseClock(text) {
  const parts = String(text || "").trim().split(":").map(Number);
  if (!parts.length || parts.length > 3 || parts.some((p) => !Number.isFinite(p) || p < 0)) return null;
  return parts.reduce((total, p) => total * 60 + p, 0);
}

export function formatLap(seconds) {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  return m ? `${m}:${(seconds - m * 60).toFixed(3).padStart(6, "0")}` : seconds.toFixed(3);
}

export function formatDelta(value) {
  if (value == null) return "—";
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(3)}`;
}

export function formatGap(value) {
  if (value == null) return "—";
  return `+${value.toFixed(3)}`;
}
