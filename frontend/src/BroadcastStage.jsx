import { useMemo, useState } from "react";
import { Video } from "lucide-react";
import PitWall from "./PitWall.jsx";
import {
  compoundInfo, formatDelta, formatGap, formatLap, raceStatus, sectorBoard, standings,
} from "./replayModel.js";

function TyreBadge({ compound, size = 22 }) {
  const c = compoundInfo(compound);
  return (
    <span className="tyre-badge" style={{ width: size, height: size, borderColor: c.color, color: c.color }} title={c.label}>
      {c.letter}
    </span>
  );
}

export function RaceOrderCard({ rows, focus, onFocus, status }) {
  const top = rows.filter((r) => r.position != null).slice(0, 5);
  return (
    <section className="glass order-card">
      <header><span>RACE ORDER</span><span>GAP TO LEADER</span></header>
      {top.length === 0 && <p className="empty-note">Order appears once cars are on track.</p>}
      {top.map((r) => (
        <button type="button" key={r.number} className={`order-row ${focus === r.number ? "focus" : ""}`} onClick={() => onFocus(r.number)}>
          <b>{r.position}</b>
          <i style={{ background: r.color }} />
          <strong>{r.code}</strong>
          <span>{r.position === 1 ? "LEADER" : formatGap(r.gap)}</span>
          {r.stint ? <TyreBadge compound={r.stint.compound} /> : <span className="tyre-badge empty" />}
        </button>
      ))}
      <footer className={`status ${status.tone}`}><span /> {status.label.toUpperCase()}</footer>
    </section>
  );
}

export function SectorCard({ driver, board }) {
  const cell = (label, s) => (
    <div>
      <small>{label}</small>
      <strong>{s && s.value != null ? s.value.toFixed(3) : "—"}</strong>
      <em className={s && s.delta != null ? (s.delta <= 0 ? "good" : "bad") : ""}>{formatDelta(s && s.delta)}</em>
    </div>
  );
  return (
    <section className="glass sector-card">
      <header><span>SECTOR TIMES</span><span>{driver ? driver.code : "—"}</span></header>
      {board ? (
        <>
          <div className="sector-grid">{cell("SECTOR 1", board.s1)}{cell("SECTOR 2", board.s2)}{cell("SECTOR 3", board.s3)}</div>
          <div className="lap-line">
            <small>LAP {board.lap}</small>
            <strong>{formatLap(board.lapTime)}</strong>
            <em className={board.lapDelta != null ? (board.lapDelta <= 0 ? "good" : "bad") : ""}>{formatDelta(board.lapDelta)}</em>
          </div>
          <p className="foot-note">Deltas are against this driver&apos;s own earlier best sectors.</p>
        </>
      ) : (
        <p className="empty-note">No completed lap yet.</p>
      )}
    </section>
  );
}

export function StintCard({ driver, stint, board, totalLaps }) {
  const c = compoundInfo(stint?.compound);
  return (
    <section className="glass stint-card">
      <header><span>CURRENT STINT</span><span>{driver ? driver.name : "—"}</span></header>
      {stint ? (
        <div className="stint-body">
          <TyreBadge compound={stint.compound} size={54} />
          <div>
            <strong>{c.label.toUpperCase()}</strong>
            <small>{stint.tyre_age} LAPS OLD · STINT {stint.stint_number}</small>
            <div className="stint-bar" title="Tyre age as a share of the race distance">
              <span style={{ width: `${Math.min(100, (stint.tyre_age / (totalLaps || 60)) * 100)}%`, background: c.color }} />
            </div>
          </div>
          {board && board.speedTrap != null && (
            <div className="trap"><strong>{board.speedTrap}</strong><small>KM/H SPEED TRAP</small></div>
          )}
        </div>
      ) : (
        <p className="empty-note">No tyre data yet.</p>
      )}
    </section>
  );
}

export function TrackCard({ store, status }) {
  const w = store.weather?.data;
  return (
    <section className="glass track-card">
      <header><span>TRACK</span><span className={`pill ${status.tone}`}>{status.label}</span></header>
      {w ? (
        <div className="weather-grid">
          <div><strong>{w.air_temperature?.toFixed(1)}°</strong><small>AIR</small></div>
          <div><strong>{w.track_temperature?.toFixed(1)}°</strong><small>TRACK</small></div>
          <div><strong>{Math.round(w.humidity)}%</strong><small>HUMIDITY</small></div>
          <div><strong>{w.rainfall ? "WET" : "DRY"}</strong><small>{w.wind_speed?.toFixed(1)} M/S WIND</small></div>
        </div>
      ) : (
        <p className="empty-note">No weather reading yet.</p>
      )}
    </section>
  );
}

export default function BroadcastStage({ replay, analytics, video, onShowSql }) {
  const { store, drivers, active } = replay;
  const rows = useMemo(() => standings(store, drivers), [store, drivers]);
  const [picked, setPicked] = useState(null);
  const focus = picked ?? rows.find((r) => r.position === 1)?.number ?? rows[0]?.number ?? null;
  const focusRow = rows.find((r) => r.number === focus) || null;
  const board = focus != null ? sectorBoard(store, focus) : null;
  const status = raceStatus(store);

  return (
    <section className="stage" id="broadcast" aria-label="Broadcast view">
      <div className="stage-backdrop">
        {video.src ? (
          // eslint-disable-next-line react-hooks/refs -- `attach` is a callback ref (the supported pattern); nothing reads a ref here
          <video ref={video.attach} src={video.src} controls playsInline />
        ) : (
          <div className="stage-hint">
            <Video size={22} />
            <strong>{active ? "Live data overlay" : "Broadcast view"}</strong>
            <span>
              {active
                ? "Load a recording you have the right to watch (below) to sync it with the replay."
                : "Start a replay to see the order, sectors, stints and the Pit Wall come alive."}
            </span>
          </div>
        )}
      </div>

      <div className="stage-left">
        <RaceOrderCard rows={rows} focus={focus} onFocus={setPicked} status={status} />
        <SectorCard driver={focusRow} board={board} />
      </div>

      <div className="stage-right">
        <PitWall replay={replay} analytics={analytics} onShowSql={onShowSql} />
      </div>

      <div className="stage-bottom">
        <StintCard driver={focusRow} stint={focusRow?.stint} board={board} totalLaps={replay.server?.total_laps} />
        <TrackCard store={store} status={status} />
      </div>
    </section>
  );
}
