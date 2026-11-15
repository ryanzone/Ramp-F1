import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import { useReplay } from "../useReplay.js";
import { useAnalytics } from "../useAnalytics.js";
import PitWall from "../PitWall.jsx";
import { RaceOrderCard, SectorCard, StintCard, TrackCard } from "../BroadcastStage.jsx";
import { formatClock, parseClock, raceStatus, sectorBoard, standings } from "../replayModel.js";

const SPEEDS = [1, 2, 5, 10];

const load = (key, fallback) => {
  try {
    const v = localStorage.getItem(`ramp.overlay.${key}`);
    return v == null ? fallback : JSON.parse(v);
  } catch {
    return fallback;
  }
};
const save = (key, value) => {
  try {
    localStorage.setItem(`ramp.overlay.${key}`, JSON.stringify(value));
  } catch {
    /* storage unavailable */
  }
};
const noop = () => {};

// The server pushes the clock twice a second; extrapolate between messages so the HUD ticks smoothly.
function useElapsed(replay) {
  const { server, serverAt } = replay;
  const playing = server?.state === "playing";
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!playing) return undefined;
    const id = setInterval(() => setNow(performance.now()), 200);
    return () => clearInterval(id);
  }, [playing]);
  if (!server) return 0;
  if (!playing) return server.elapsed;
  return Math.min(server.duration, server.elapsed + ((Math.max(now, serverAt) - serverAt) / 1000) * server.speed);
}

export default function Overlay() {
  const bridge = window.overlay; // undefined in a plain browser tab
  const replay = useReplay();
  const [races, setRaces] = useState([]);
  const [sessionId, setSessionId] = useState(() => load("session", ""));
  const [opacity, setOpacity] = useState(() => load("opacity", 1));
  const [showSettings, setShowSettings] = useState(false);
  const [locked, setLocked] = useState(false);
  const [jump, setJump] = useState("");
  const [jumpError, setJumpError] = useState("");
  const [picked, setPicked] = useState(null);

  const { store, drivers, server } = replay;
  const rows = useMemo(() => standings(store, drivers), [store, drivers]);
  const leaders = useMemo(() => rows.filter((r) => r.position != null).slice(0, 2).map((r) => r.code), [rows]);
  const analytics = useAnalytics(replay.replayId, server, leaders);
  const elapsed = useElapsed(replay);
  const playing = server?.state === "playing";
  const duration = server?.duration || 0;
  const status = raceStatus(store);
  const focus = picked ?? rows.find((r) => r.position === 1)?.number ?? rows[0]?.number ?? null;
  const focusRow = rows.find((r) => r.number === focus) || null;
  const board = focus != null ? sectorBoard(store, focus) : null;

  useEffect(() => {
    api.races().then((list) => {
      setRaces(list);
      setSessionId((current) => (current && list.some((r) => String(r.session_id) === String(current)) ? current : list.length ? String(list[0].session_id) : ""));
    }).catch(() => setRaces([]));
  }, []);
  useEffect(() => save("session", sessionId), [sessionId]);
  useEffect(() => {
    save("opacity", opacity);
    bridge?.setOpacity(opacity);
  }, [opacity, bridge]);

  // Keep the cursor in the Pit Wall box so the next question can be typed straight away.
  const focusAsk = useCallback(() => document.querySelector(".pw-input input")?.focus(), []);
  useEffect(() => {
    if (!analytics.busy && document.hasFocus() && replay.active) focusAsk();
  }, [analytics.busy, replay.active, focusAsk]);

  // Global hotkeys (work while the race video has focus) arrive as commands from the main process.
  const elapsedRef = useRef(0);
  useEffect(() => {
    elapsedRef.current = elapsed;
  });
  const seekBy = useCallback(
    (delta) => replay.seek(Math.min(duration, Math.max(0, elapsedRef.current + delta))),
    [replay, duration],
  );
  useEffect(
    () =>
      bridge?.onCommand((cmd) => {
        if (cmd === "toggle") (playing ? replay.pause : replay.play)();
        else if (cmd === "seek:-5") seekBy(-5);
        else if (cmd === "seek:+5") seekBy(5);
        else if (cmd === "seek:-1") seekBy(-1);
        else if (cmd === "seek:+1") seekBy(1);
        else if (cmd === "ask") focusAsk();
        else if (cmd === "locked:true") setLocked(true);
        else if (cmd === "locked:false") setLocked(false);
      }),
    [bridge, playing, replay, seekBy, focusAsk],
  );

  // Transparent areas let clicks reach the video underneath; only the HUD panels capture the mouse.
  useEffect(() => {
    if (!bridge) return undefined;
    let over = false;
    const onMove = (e) => {
      const hit = !!e.target.closest?.("[data-hit]");
      if (hit !== over) {
        over = hit;
        bridge.setHit(hit);
      }
    };
    document.addEventListener("mousemove", onMove);
    return () => document.removeEventListener("mousemove", onMove);
  }, [bridge]);

  const submitJump = (event) => {
    event.preventDefault();
    const seconds = parseClock(jump);
    if (seconds == null || seconds > duration) {
      setJumpError(`h:mm:ss up to ${formatClock(duration)}`);
      return;
    }
    setJumpError("");
    replay.seek(seconds);
    setJump("");
  };

  return (
    <div className={`hud ${locked ? "locked" : ""}`}>
      <header className="hud-bar" data-hit>
        <b className="logo">RAMP</b>
        {replay.active ? (
          <>
            <span className="lap">LAP {server?.current_lap ?? 0}{server?.total_laps ? `/${server.total_laps}` : ""}</span>
            <span className={`flag tone-${status.tone}`}>{status.label}</span>
            <span className="clock">{formatClock(elapsed)}</span>
          </>
        ) : (
          <span className="dim">no replay running</span>
        )}
        <span className="spacer" />
        {replay.active && (
          <>
            <button title="Back 5s (Ctrl+Shift+Left)" onClick={() => seekBy(-5)}>−5s</button>
            <button title="Play / pause (Ctrl+Shift+Space)" onClick={() => (playing ? replay.pause() : replay.play())}>
              {playing ? "❚❚" : "▶"}
            </button>
            <button title="Forward 5s (Ctrl+Shift+Right)" onClick={() => seekBy(5)}>+5s</button>
          </>
        )}
        <button title="Settings" className={showSettings ? "on" : ""} onClick={() => setShowSettings(!showSettings)}>⚙</button>
        <button title="Lock: click through everything (Ctrl+Shift+C)" className={locked ? "on" : ""}
          onClick={() => bridge?.setLocked(!locked)}>🔒</button>
        <button title="Quit" onClick={() => bridge?.quit()}>✕</button>
      </header>

      {showSettings && (
        <section className="hud-card" data-hit>
          {!replay.active ? (
            <div className="row">
              <select value={sessionId} onChange={(e) => setSessionId(e.target.value)}>
                {races.map((r) => <option key={r.session_id} value={r.session_id}>{r.race_name}</option>)}
              </select>
              <button disabled={!sessionId || replay.status === "starting"} onClick={() => replay.start(Number(sessionId), true)}>
                {replay.status === "starting" ? "Loading…" : "Start replay"}
              </button>
            </div>
          ) : (
            <>
              <div className="row">
                <small>Sync</small>
                <button onClick={() => seekBy(-5)}>−5s</button>
                <button onClick={() => seekBy(-1)}>−1s</button>
                <button onClick={() => seekBy(1)}>+1s</button>
                <button onClick={() => seekBy(5)}>+5s</button>
                <button onClick={() => replay.reset()}>⟲</button>
              </div>
              <form className="row" onSubmit={submitJump}>
                <small>Jump</small>
                <input value={jump} onChange={(e) => setJump(e.target.value)} placeholder="h:mm:ss" />
                <button type="submit">Go</button>
                {jumpError && <small className="err">{jumpError}</small>}
              </form>
              <div className="row">
                <small>Speed</small>
                {SPEEDS.map((s) => (
                  <button key={s} className={server?.speed === s ? "on" : ""} onClick={() => replay.setSpeed(s)}>{s}x</button>
                ))}
                <button onClick={replay.stop}>Stop</button>
              </div>
            </>
          )}
          <div className="row">
            <small>Opacity</small>
            <input type="range" min={0.3} max={1} step={0.05} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} />
          </div>
          <small className="dim">Ctrl+Shift: Space play/pause · ←/→ ±5s · Q ask · O hide · C lock. Ctrl+Alt+←/→ ±1s</small>
        </section>
      )}
      {replay.error && <div className="hud-card err" data-hit>{replay.error}</div>}

      {replay.active && (
        <>
          <div className="col-left" data-hit>
            <RaceOrderCard rows={rows} focus={focus} onFocus={setPicked} status={status} />
            <SectorCard driver={focusRow} board={board} />
          </div>

          <div className="col-bottom" data-hit>
            <StintCard driver={focusRow} stint={focusRow?.stint} board={board} totalLaps={server?.total_laps} />
            <TrackCard store={store} status={status} />
          </div>
        </>
      )}

      <div className="col-right" data-hit>
        <PitWall replay={replay} analytics={analytics} onShowSql={noop} />
      </div>
    </div>
  );
}
