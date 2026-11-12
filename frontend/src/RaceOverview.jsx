import { useMemo } from "react";
import { Flag } from "lucide-react";
import { compoundInfo, formatGap, formatLap, raceStatus, standings } from "./replayModel.js";

export default function RaceOverview({ replay }) {
  const { store, drivers, server, active } = replay;
  const rows = useMemo(() => standings(store, drivers), [store, drivers]);
  const status = raceStatus(store);
  const leader = rows.find((r) => r.position === 1);
  const w = store.weather?.data;

  return (
    <section className="panel overview-panel" id="race-overview">
      <div className="panel-heading">
        <div>
          <div className="panel-kicker">RACE OVERVIEW / 01</div>
          <h2>{active ? "Standings at the replay clock" : "Race overview"}</h2>
          <p>{active ? "Built only from events released so far." : "Start a replay to see the order develop."}</p>
        </div>
        <Flag size={18} className="muted-icon" />
      </div>

      {!active ? (
        <div className="empty-state">
          <div className="empty-icon"><Flag size={21} /></div>
          <strong>No replay running</strong>
          <span>Start the replay above to follow the leader, the order, tyres and race status as they happen.</span>
        </div>
      ) : (
        <>
          <div className="overview-tiles">
            <div><small>RACE</small><strong>{server?.race_name || "—"}</strong></div>
            <div><small>LAP</small><strong>{server?.current_lap ?? 0}{server?.total_laps ? ` / ${server.total_laps}` : ""}</strong></div>
            <div><small>LEADER</small><strong>{leader ? leader.code : "—"}</strong></div>
            <div><small>STATUS</small><strong className={`tone-${status.tone}`}>{status.label}</strong></div>
            <div><small>WEATHER</small>
              <strong>{w ? `${w.air_temperature?.toFixed(0)}° air · ${w.track_temperature?.toFixed(0)}° track${w.rainfall ? " · wet" : ""}` : "—"}</strong></div>
          </div>

          <div className="standings-wrap">
            <table className="standings">
              <thead>
                <tr><th>Pos</th><th>Driver</th><th>Team</th><th>Gap</th><th>Interval</th><th>Tyre</th><th>Last lap</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.number}>
                    <td className="num">{r.position ?? "—"}</td>
                    <td><i className="team-bar" style={{ background: r.color }} />{r.code} <small>{r.name}</small></td>
                    <td>{r.team}</td>
                    <td className="num">{r.position === 1 ? "Leader" : formatGap(r.gap)}</td>
                    <td className="num">{r.position === 1 ? "—" : formatGap(r.interval)}</td>
                    <td>
                      {r.stint ? (
                        <span className="tyre-cell" style={{ color: compoundInfo(r.stint.compound).color }}>
                          ● {compoundInfo(r.stint.compound).letter} <small>{r.stint.tyre_age}L</small>
                        </span>
                      ) : "—"}
                    </td>
                    <td className="num">{formatLap(r.lastLap)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
