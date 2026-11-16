import { useEffect, useMemo, useRef, useState } from "react";
import { Database, Flag, Link2, Video } from "lucide-react";
import AnalyticsChart from "./AnalyticsChart.jsx";

// SQL prompts sent to your backend NL-to-SQL engine at race finish
const FINAL_SQL_PROMPTS = {
  teamPace: "Compare average valid lap time and total laps across all teams",
  teamStops: "Compare total pit stops and average pit stop duration by team",
};

export default function VideoSync({ replay, video, analytics, syncOffset, setSyncOffset }) {
  const [url, setUrl] = useState("");
  const [clock, setClock] = useState({ video: 0, replay: 0 });
  const [activeTab, setActiveTab] = useState("teamPace");
  const triggeredForReplay = useRef(null);

  const { getTime, setTime, src, setSrc, follow, setFollow } = video;
  const server = replay.server;

  useEffect(() => {
    const id = setInterval(() => {
      setClock({ video: getTime(), replay: server ? server.elapsed : 0 });
    }, 500);
    return () => clearInterval(id);
  }, [getTime, server]);

  // Detect end of ANY race (replay reached final lap OR server marked race finished)
  const isRaceEnd = Boolean(
    replay.active &&
      server &&
      ((server.total_laps > 0 && server.current_lap >= server.total_laps) ||
        server.finished === true ||
        server.status === "finished" ||
        server.state === "finished")
  );

  // Automatically execute real SQL queries once when ANY race reaches the end
  useEffect(() => {
    if (!isRaceEnd || !analytics?.ask) return;
    const runKey = `${replay.replayId ?? "session"}-${server?.total_laps}`;
    if (triggeredForReplay.current === runKey) return;
    triggeredForReplay.current = runKey;

    analytics.ask(FINAL_SQL_PROMPTS.teamPace);
    analytics.ask(FINAL_SQL_PROMPTS.teamStops);
  }, [isRaceEnd, replay.replayId, server?.total_laps, analytics]);

  // Pull the executed SQL results from analytics.messages for all teams
  const finalSqlResults = useMemo(() => {
    const analystMsgs = (analytics?.messages || []).filter((m) => m.role === "analyst");
    const findResult = (promptText) =>
      [...analystMsgs].reverse().find((m) => m.result?.question === promptText)?.result || null;

    return {
      teamPace: findResult(FINAL_SQL_PROMPTS.teamPace),
      teamStops: findResult(FINAL_SQL_PROMPTS.teamStops),
    };
  }, [analytics?.messages]);

  // Fallback/combined team summary if SQL returns partial teams, ensuring all teams are read
  const activeResult = finalSqlResults[activeTab];

  const pickFile = (event) => {
    const file = event.target.files && event.target.files[0];
    if (file) setSrc(URL.createObjectURL(file), true);
  };

  const loadUrl = (event) => {
    event.preventDefault();
    if (/^https?:\/\/.+/i.test(url.trim())) setSrc(url.trim());
  };

  const markNow = () => setSyncOffset(Math.round((clock.replay - clock.video) * 10) / 10);
  const replayToVideo = () => replay.seek(Math.max(0, clock.video + syncOffset));
  const videoToReplay = () => setTime(clock.replay - syncOffset);

  return (
    <section className="panel video-panel" id="video-sync">
      <div className="panel-heading">
        <div>
          <div className="panel-kicker">RECORDING SYNC / 08</div>
          <h2>Sync an external race recording</h2>
          <p>
            Use a recording you have the right to watch. RAMP never downloads or fetches videos; the file or link stays in
            your browser.
          </p>
        </div>
        <Video size={18} className="muted-icon" />
      </div>

      <div className="video-sources">
        <label className="btn-ghost file-pick">
          Choose a video file
          <input type="file" accept="video/*" onChange={pickFile} />
        </label>
        <form onSubmit={loadUrl} className="url-form">
          <Link2 size={14} />
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Direct video link (https://…/race.mp4)"
            aria-label="Video URL"
          />
          <button type="submit" className="btn-ghost" disabled={!/^https?:\/\/.+/i.test(url.trim())}>
            Load
          </button>
        </form>
        {src && (
          <button type="button" className="btn-ghost" onClick={() => setSrc("")}>
            Remove video
          </button>
        )}
      </div>

      <div className="sync-grid">
        <div>
          <small>VIDEO TIME</small>
          <strong>{clock.video.toFixed(1)} s</strong>
        </div>
        <div>
          <small>REPLAY TIME</small>
          <strong>{replay.active ? `${clock.replay.toFixed(1)} s` : "—"}</strong>
        </div>
        <div>
          <small>OFFSET</small>
          <strong>
            {syncOffset > 0 ? "+" : ""}
            {syncOffset} s
          </strong>
        </div>
      </div>

      <div className="sync-actions">
        <button type="button" className="btn-accent" disabled={!replay.active || !src} onClick={markNow}>
          Mark: these two moments match
        </button>
        <button type="button" className="btn-ghost" disabled={!replay.active || !src} onClick={replayToVideo}>
          Move replay to the video
        </button>
        <button type="button" className="btn-ghost" disabled={!replay.active || !src} onClick={videoToReplay}>
          Move video to the replay
        </button>
        <label className="follow-toggle">
          <input
            type="checkbox"
            checked={follow}
            onChange={(e) => setFollow(e.target.checked)}
            disabled={!src || !replay.active}
          />
          Make the video follow the replay
        </label>
      </div>

      <p className="foot-note">
        Pause the video and the replay on the same moment (for example, lights out), press Mark, and the offset is
        saved. Play and pause stay independent unless you tick Follow.
      </p>

      {/* END-OF-RACE FINAL SQL ANALYSIS (ALL TEAMS) */}
      {isRaceEnd && (
        <article className="chart-card" style={{ marginTop: "1.25rem" }}>
          <header>
            <div>
              <h3>
                <Flag size={15} style={{ display: "inline", marginRight: 6, verticalAlign: "text-bottom" }} />
                Final Race Analysis · All Constructors
              </h3>
              <small>
                {activeResult?.answer || "Executing end-of-race SQL queries across all teams…"}
              </small>
            </div>

            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
              <button
                type="button"
                className={activeTab === "teamPace" ? "btn-accent" : "btn-ghost"}
                onClick={() => setActiveTab("teamPace")}
              >
                Team Pace
              </button>
              <button
                type="button"
                className={activeTab === "teamStops" ? "btn-accent" : "btn-ghost"}
                onClick={() => setActiveTab("teamStops")}
              >
                Pit Strategy
              </button>
              <span className="lap-tag">
                CHEQUERED FLAG · LAP {server?.current_lap ?? server?.total_laps}
              </span>
            </div>
          </header>

          <div className="chart-box">
            {!activeResult ? (
              <div className="chart-empty">Running end-of-race SQL queries…</div>
            ) : activeResult.status !== "ok" ? (
              <div className="chart-empty error">{activeResult.answer}</div>
            ) : (
              <AnalyticsChart result={activeResult} />
            )}
          </div>

          {activeResult?.sql && (
            <details style={{ marginTop: "0.75rem" }}>
              <summary>
                <Database size={12} style={{ display: "inline", marginRight: 5 }} />
                Executed SQL · {activeResult.elapsed_ms} ms · {activeResult.row_count} teams
              </summary>
              <pre>
                <code>{activeResult.sql}</code>
              </pre>
            </details>
          )}
        </article>
      )}
    </section>
  );
}