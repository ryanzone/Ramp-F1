import { useEffect, useState } from "react";
import { Link2, Video } from "lucide-react";

export default function VideoSync({ replay, video, syncOffset, setSyncOffset }) {
  const [url, setUrl] = useState("");
  const [clock, setClock] = useState({ video: 0, replay: 0 });
  const { getTime, setTime, src, setSrc, follow, setFollow } = video;
  const server = replay.server;

  useEffect(() => {
    const id = setInterval(() => {
      setClock({ video: getTime(), replay: server ? server.elapsed : 0 });
    }, 500);
    return () => clearInterval(id);
  }, [getTime, server]);

  const pickFile = (event) => {
    const file = event.target.files && event.target.files[0];
    if (file) setSrc(URL.createObjectURL(file), true);
  };
  const loadUrl = (event) => {
    event.preventDefault();
    if (/^https?:\/\/.+/i.test(url.trim())) setSrc(url.trim());
  };
  // replay time = video time + offset
  const markNow = () => setSyncOffset(Math.round((clock.replay - clock.video) * 10) / 10);
  const replayToVideo = () => replay.seek(Math.max(0, clock.video + syncOffset));
  const videoToReplay = () => {
    setTime(clock.replay - syncOffset);
  };

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
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Direct video link (https://…/race.mp4)" aria-label="Video URL" />
          <button type="submit" className="btn-ghost" disabled={!/^https?:\/\/.+/i.test(url.trim())}>Load</button>
        </form>
        {src && <button type="button" className="btn-ghost" onClick={() => setSrc("")}>Remove video</button>}
      </div>

      <div className="sync-grid">
        <div><small>VIDEO TIME</small><strong>{clock.video.toFixed(1)} s</strong></div>
        <div><small>REPLAY TIME</small><strong>{replay.active ? `${clock.replay.toFixed(1)} s` : "—"}</strong></div>
        <div><small>OFFSET</small><strong>{syncOffset > 0 ? "+" : ""}{syncOffset} s</strong></div>
      </div>

      <div className="sync-actions">
        <button type="button" className="btn-accent" disabled={!replay.active || !src} onClick={markNow}>
          Mark: these two moments match
        </button>
        <button type="button" className="btn-ghost" disabled={!replay.active || !src} onClick={replayToVideo}>Move replay to the video</button>
        <button type="button" className="btn-ghost" disabled={!replay.active || !src} onClick={videoToReplay}>Move video to the replay</button>
        <label className="follow-toggle">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} disabled={!src || !replay.active} />
          Make the video follow the replay
        </label>
      </div>
      <p className="foot-note">
        Pause the video and the replay on the same moment (for example, lights out), press Mark, and the offset is
        saved. Play and pause stay independent unless you tick Follow.
      </p>
    </section>
  );
}
