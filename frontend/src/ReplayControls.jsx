import { useEffect, useState } from "react";
import { Clock, Pause, Play, RotateCcw, SkipBack, SkipForward, Video } from "lucide-react";
import { formatClock, parseClock } from "./replayModel.js";

const SPEEDS = [0.5, 1, 2, 5, 10];

// The backend only pushes the clock twice a second; between messages we extrapolate it
// locally (same speed, same start) so the slider and timer move smoothly.
function useSmoothElapsed(replay) {
  const { server, serverAt } = replay;
  const playing = server?.state === "playing";
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!playing) return undefined;
    const id = setInterval(() => setNow(performance.now()), 100);
    return () => clearInterval(id);
  }, [playing]);
  if (!server) return 0;
  if (!playing) return server.elapsed;
  return Math.min(server.duration, server.elapsed + (Math.max(now, serverAt) - serverAt) / 1000 * server.speed);
}

export default function ReplayControls({ replay, raceName, sessionId, syncOffset, setSyncOffset }) {
  const { server, status, error, connected } = replay;
  const elapsed = useSmoothElapsed(replay);
  const [drag, setDrag] = useState(null);
  const [jump, setJump] = useState("");
  const [jumpError, setJumpError] = useState("");

  if (!replay.active) {
    return (
      <section className="panel replay-panel" id="replay">
        <div className="panel-heading">
          <div>
            <div className="panel-kicker">HISTORICAL REPLAY / 00</div>
            <h2>Replay the race as if it were live</h2>
            <p>
              Events are released at their original timestamps. Analytics, charts and the Pit Wall only see data up
              to the replay clock.
            </p>
          </div>
          <button
            type="button"
            className="btn-accent"
            disabled={!sessionId || status === "starting"}
            onClick={() => replay.start(sessionId, true)}
          >
            <Play size={15} /> {status === "starting" ? "Loading race…" : `Start replay${raceName ? ` · ${raceName}` : ""}`}
          </button>
        </div>
        {error && <div className="inline-error" role="alert">{error}</div>}
        <p className="footnote">
          Until a replay starts, the panels below show the complete race. Starting one switches them to what is known
          at the replay clock.
        </p>
      </section>
    );
  }

  const duration = server?.duration || 1;
  const shown = drag ?? elapsed;
  const playing = server?.state === "playing";
  const commit = () => {
    if (drag != null) replay.seek(drag);
    setDrag(null);
  };
  const nudge = (seconds) => replay.seek(Math.min(duration, Math.max(0, elapsed + seconds)));
  const submitJump = (event) => {
    event.preventDefault();
    const seconds = parseClock(jump);
    if (seconds == null || seconds > duration) {
      setJumpError(`Enter a time between 0:00:00 and ${formatClock(duration)} (h:mm:ss).`);
      return;
    }
    setJumpError("");
    replay.seek(seconds);
    setJump("");
  };
  const raceClock = server ? new Date(new Date(server.start).getTime() + shown * 1000).toISOString().slice(11, 19) : "—";

  return (
    <section className="panel replay-panel" id="replay">
      <div className="panel-heading">
        <div>
          <div className="panel-kicker">HISTORICAL REPLAY / 00</div>
          <h2>{server?.race_name || raceName || "Replay"}</h2>
          <p>
            <span className={`conn-dot ${connected ? "on" : ""}`} />
            {connected ? "Streaming from the replay engine" : "Reconnecting…"} · lap {server?.current_lap ?? 0}
            {server?.total_laps ? ` of ${server.total_laps}` : ""}
          </p>
        </div>
        <button type="button" className="btn-ghost" onClick={replay.stop}>End replay</button>
      </div>

      {error && <div className="inline-error" role="alert">{error}</div>}

      <div className="replay-row">
        <button type="button" className="btn-accent" onClick={playing ? replay.pause : replay.play}
          disabled={!playing && server?.finished}>
          {playing ? <Pause size={15} /> : <Play size={15} />}
          {playing ? "Pause" : server?.finished ? "Finished" : elapsed > 0 ? "Resume" : "Play"}
        </button>
        <button type="button" className="btn-ghost" onClick={replay.reset}><RotateCcw size={14} /> Reset</button>
        <div className="seek-group" aria-label="Seek">
          <button type="button" onClick={() => nudge(-60)} title="Back 60 seconds"><SkipBack size={13} /> 60s</button>
          <button type="button" onClick={() => nudge(-10)} title="Back 10 seconds">−10s</button>
          <button type="button" onClick={() => nudge(10)} title="Forward 10 seconds">+10s</button>
          <button type="button" onClick={() => nudge(60)} title="Forward 60 seconds">60s <SkipForward size={13} /></button>
        </div>
        <div className="speed-group" role="group" aria-label="Playback speed">
          {SPEEDS.map((s) => (
            <button key={s} type="button" className={server?.speed === s ? "on" : ""} onClick={() => replay.setSpeed(s)}>{s}×</button>
          ))}
        </div>
        <div className="replay-time" aria-live="off">
          <Clock size={14} /> {formatClock(shown)} <span>/ {formatClock(duration)}</span>
        </div>
      </div>

      <input
        className="timeline"
        type="range"
        aria-label="Replay timeline"
        min={0}
        max={duration}
        step={1}
        value={Math.min(shown, duration)}
        style={{ "--progress": `${Math.min(100, (shown / duration) * 100)}%` }}
        onChange={(e) => setDrag(Number(e.target.value))}
        onPointerUp={commit}
        onKeyUp={commit}
        onBlur={commit}
      />
      <div className="replay-meta">
        <span>Race clock {raceClock} UTC</span>
        <span>{Math.round((shown / duration) * 100)}% of the race</span>
        <span>Lap {server?.current_lap ?? 0}{server?.total_laps ? ` / ${server.total_laps}` : ""}</span>
      </div>

      <div className="replay-tools">
        <form onSubmit={submitJump} className="jump-form">
          <label>
            Jump to time
            <input value={jump} onChange={(e) => setJump(e.target.value)} placeholder="h:mm:ss" inputMode="numeric" />
          </label>
          <button type="submit" className="btn-ghost">Go</button>
          {jumpError && <span className="inline-error small">{jumpError}</span>}
        </form>
        <div className="offset-form">
          <label>
            <Video size={13} /> Video sync offset (s)
            <input type="number" step="0.5" value={syncOffset} onChange={(e) => setSyncOffset(Number(e.target.value) || 0)} />
          </label>
          {[-5, -0.5, 0.5, 5].map((d) => (
            <button key={d} type="button" className="btn-ghost small" onClick={() => setSyncOffset(Math.round((syncOffset + d) * 10) / 10)}>
              {d > 0 ? `+${d}` : d}
            </button>
          ))}
          <span className="hint">replay time = video time + offset</span>
        </div>
      </div>
    </section>
  );
}
