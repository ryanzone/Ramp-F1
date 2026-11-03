
import { useMemo, useState, useEffect } from "react";
import {
  Activity,
  Flag,
  Gauge,
  Timer,
  Layers3,
  Radio,
  Search,
  ChevronDown,
  ArrowUpRight,
  Menu,
  X,
  Database,
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { api } from "./api.js";
import "./index.css";

const PALETTE = [
  "#4788ef",
  "#ff914d",
  "#ff4d62",
  "#bd7aff",
  "#ffd166",
  "#49d7cb",
  "#e10600",
  "#56c78b",
];

function mapDrivers(driverRows, lapRows, resultRows = []) {
  const byCode = {};
  lapRows.forEach((l) => {
    const t = Number(l.lap_time_seconds);
    const valid = l.is_valid !== false && Number.isFinite(t) && t > 0 && t < 300;
    if (!valid) return;
    if (!byCode[l.driver_code]) byCode[l.driver_code] = [];
    byCode[l.driver_code].push(t);
  });
  const statusByCode = {};
  resultRows.forEach((r) => {
    if (r.driver_code && r.status) statusByCode[r.driver_code] = String(r.status).toUpperCase();
  });
  return driverRows
    .map((d, i) => {
      const times = byCode[d.driver_code] || [];
      const avg = times.length ? times.reduce((a, b) => a + b, 0) / times.length : null;
      return {
        code: d.driver_code,
        name: d.driver_name,
        team: d.team_name,
        color: PALETTE[i % PALETTE.length],
        avg,
        status: statusByCode[d.driver_code] || null,
      };
    })
    .sort((a, b) => (a.avg == null ? 1 : b.avg == null ? -1 : a.avg - b.avg) || a.code.localeCompare(b.code));
}

function buildChartData(drivers, laps, selected, limit) {
  const byLap = {};
  laps.forEach((l) => {
    const t = Number(l.lap_time_seconds);
    if (l.is_valid === false || !Number.isFinite(t) || t <= 0 || t >= 300) return;
    if (!byLap[l.lap_number]) byLap[l.lap_number] = {};
    byLap[l.lap_number][l.driver_code] = t;
  });
  const codes = new Set(selected);
  return Object.entries(byLap)
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .slice(0, Number(limit))
    .map(([lap, times]) => {
      const row = { lap: Number(lap) };
      drivers.forEach((d) => {
        if (codes.has(d.code)) row[d.code] = times[d.code];
      });
      return row;
    });
}

function formatTime(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return String(value);
  }
}

function StatCard({ icon: Icon, label, value, note }) {
  return (
    <article className="stat-card">
      <div className="stat-top">
        <span>{label}</span>
        <Icon size={17} />
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-note">{note}</div>
    </article>
  );
}

function PanelHeading({ kicker, title, description, extra }) {
  return (
    <div className="panel-heading">
      <div>
        <div className="panel-kicker">{kicker}</div>
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {extra}
    </div>
  );
}

export default function App() {
  const [races, setRaces] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [laps, setLaps] = useState([]);
  const [pitStops, setPitStops] = useState([]);
  const [tyreStints, setTyreStints] = useState([]);
  const [raceControl, setRaceControl] = useState([]);
  const [weather, setWeather] = useState([]);
  const [selected, setSelected] = useState([]);
  const [search, setSearch] = useState("");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [sessionOpen, setSessionOpen] = useState(false);
  const [session, setSession] = useState("Select a race");
  const [sessionId, setSessionId] = useState(null);
  const [lapLimit, setLapLimit] = useState("20");
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);
  const [active, setActive] = useState("Overview");

  useEffect(() => {
    let cancelled = false;
    async function loadRaces() {
      try {
        const raceRows = await api.races();
        if (!cancelled) {
          setRaces(raceRows);
          if (raceRows.length > 0 && !sessionId) {
            const first = raceRows[0];
            setSession(first.race_name);
            setSessionId(first.session_id);
          }
        }
      } catch {
        setRaces([]);
      }
    }
    loadRaces();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  useEffect(() => {
    let cancelled = false;
    async function fetchAll() {
      setStatus("loading");
      try {
        const settled = await Promise.allSettled([
          api.drivers(sessionId), api.laps(null, sessionId), api.pitStops(sessionId),
          api.raceControl(sessionId), api.weather(sessionId), api.tyreStints(sessionId), api.results(sessionId),
        ]);
        const [driverRows, lapRows, pitRows, rcRows, weatherRows, stintRows, resultRows] = settled.map(
          (r) => r.status === "fulfilled" ? r.value : []
        );
        if (!cancelled) {
          setDrivers(mapDrivers(driverRows, lapRows, resultRows));
          setLaps(lapRows);
          setPitStops(pitRows);
          setTyreStints(stintRows);
          setRaceControl(rcRows);
          setWeather(weatherRows);
          setStatus("live");
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
          setStatus("error");
        }
      }
    }
    fetchAll();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const activeSelection =
    selected.length > 0 ? selected : drivers.slice(0, 3).map((d) => d.code);

  const visibleDrivers = useMemo(
    () =>
      drivers.filter((driver) =>
        `${driver.code} ${driver.name} ${driver.team}`
          .toLowerCase()
          .includes(search.toLowerCase())
      ),
    [search, drivers]
  );

  const chartDrivers = drivers.filter((driver) =>
    activeSelection.includes(driver.code)
  );

  const chartData = useMemo(
    () => buildChartData(drivers, laps, activeSelection, lapLimit),
    [drivers, laps, activeSelection, lapLimit]
  );

  const currentRace = races.find(
    (r) => Number(r.session_id) === Number(sessionId)
  );

  const latestWeather = weather.length
    ? weather[weather.length - 1]
    : null;

  const raceDistance =
    currentRace?.race_distance_laps ||
    (laps.length
      ? Math.max(...laps.map((l) => Number(l.lap_number)))
      : null);

  function toggleDriver(code) {
    setSelected((current) =>
      current.includes(code)
        ? current.filter((item) => item !== code)
        : [...current, code]
    );
  }

  function navigate(item) {
    setActive(item.name);
    setMobileNavOpen(false);
    document.getElementById(item.target)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  function resetDrivers() {
    setSelected([]);
    setSearch("");
  }

  function selectRace(race) {
    setSession(race.race_name);
    setSessionId(race.session_id);
    setSelected([]);
    setSearch("");
    setSessionOpen(false);
  }

  return (
    <div className="app-shell">
      {mobileNavOpen && (
        <button
          className="mobile-overlay"
          aria-label="Close navigation"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      <aside className={`sidebar ${mobileNavOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <span className="brand-mark">R</span>
          <span className="brand-name">RAMP<span className="brand-period">.</span></span>
          <button
            className="icon-button close-nav"
            onClick={() => setMobileNavOpen(false)}
            aria-label="Close menu"
          >
            <X size={18} />
          </button>
        </div>

        <div className="side-label">WORKSPACE</div>

        <nav className="sidebar-nav" aria-label="Dashboard sections">
          {[
            { name: "Overview", icon: Gauge, target: "overview" },
            { name: "Lap analysis", icon: Activity, target: "lap-analysis" },
            { name: "Tyre strategy", icon: Layers3, target: "tyre-strategy" },
            { name: "Pit stops", icon: Timer, target: "pit-stops" },
            { name: "Race control", icon: Radio, target: "race-control" },
          ].map(({ name, icon: Icon, target }) => (
            <button
              key={name}
              className={`nav-item ${active === name ? "active" : ""}`}
              onClick={() => navigate({ name, target })}
              aria-current={active === name ? "page" : undefined}
            >
              <Icon size={18} />
              <span>{name}</span>
              {active === name && <span className="nav-indicator" />}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="status-dot" />
          <div>
            <strong>Analysis workspace</strong>
            <span>Historical data mode</span>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label="Open navigation"
            onClick={() => setMobileNavOpen(true)}
          >
            <Menu size={20} />
          </button>

          <div className="breadcrumb">
            RAMP <span>/</span> {active}
          </div>

          <div className="topbar-right">
            <span className="data-badge">
              <span />
              {status === "loading"
                ? "LOADING DATA"
                : status === "error"
                  ? "API ERROR"
                  : "HISTORICAL DATA"}
            </span>
          </div>
        </header>

        <div className="page-content">
          <section className="page-heading" id="overview">
            <div>
              <div className="eyebrow">
                <Flag size={13} />
                {currentRace
                  ? `${currentRace.season} SEASON / RACE ANALYTICS`
                  : "2025 SEASON / RACE ANALYTICS"}
              </div>
              <h1>Race overview<span className="heading-period">.</span></h1>
              <p>Understand the race. Find the advantage.</p>
            </div>

            <div className="session-wrapper">
              <button
                className="session-select"
                onClick={() => setSessionOpen((open) => !open)}
                aria-expanded={sessionOpen}
              >
                <span className="session-dot" />
                {session}
                <ChevronDown size={16} />
              </button>

              {sessionOpen && (
                <div className="session-menu">
                  {races.map((race) => (
                    <button
                      key={race.session_id}
                      onClick={() => selectRace(race)}
                    >
                      {race.race_name}
                      {sessionId === race.session_id && <span>â\x80\xbd</span>}
                    </button>
                  ))}
                  {races.length === 0 && (
                    <p>No races available. Import data to add sessions.</p>
                  )}
                </div>
              )}
            </div>
          </section>

          <section className="stats-grid">
            <StatCard
              icon={Flag}
              label="Race distance"
              value={raceDistance ? `${raceDistance} laps` : "—"}
              note={currentRace?.circuit_name || "Circuit unavailable"}
            />
            <StatCard
              icon={Activity}
              label="Drivers tracked"
              value={drivers.length}
              note="Full race field"
            />
            <StatCard
              icon={Timer}
              label="Pit stops"
              value={pitStops.length}
              note={pitStops.length ? "Historical session data" : "No pit-stop records"}
            />
            <StatCard
              icon={Gauge}
              label="Track temperature"
              value={
                latestWeather && latestWeather.track_temperature != null
                  ? `${latestWeather.track_temperature}\u00B0C`
                  : "\u2014 \u00B0C"
              }
              note={
                latestWeather ? "Historical weather data" : "Weather unavailable"
              }
            />
          </section>

          <section className="content-grid">
            <article className="panel lap-panel" id="lap-analysis">
              <PanelHeading
                kicker="TELEMETRY / 01"
                title="Lap time evolution"
                description="Compare pace across the selected laps"
                extra={
                  <select
                    className="select-control"
                    value={lapLimit}
                    onChange={(event) => setLapLimit(event.target.value)}
                    aria-label="Number of laps to display"
                  >
                    <option value="10">10 laps</option>
                    <option value="15">15 laps</option>
                    <option value="20">20 laps</option>
                  </select>
                }
              />

              <div className="chart-legend">
                {chartDrivers.map((driver) => (
                  <button
                    key={driver.code}
                    onClick={() => toggleDriver(driver.code)}
                    title={`Hide ${driver.code}`}
                  >
                    <span style={{ background: driver.color }} />
                    {driver.code}
                    <X size={11} />
                  </button>
                ))}
                <button className="reset-button" onClick={resetDrivers}>
                  Reset
                </button>
              </div>

              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={chartData}
                    margin={{ top: 8, right: 12, left: -18, bottom: 0 }}
                  >
                    <CartesianGrid
                      stroke="#292c34"
                      strokeDasharray="3 5"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="lap"
                      tick={{ fill: "#858a97", fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      label={{
                        value: "LAP",
                        position: "insideBottomRight",
                        offset: -4,
                        fill: "#858a97",
                        fontSize: 9,
                      }}
                    />
                    <YAxis
                      domain={["dataMin - 0.8", "dataMax + 0.8"]}
                      tick={{ fill: "#858a97", fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(value) => value.toFixed(1)}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#17191f",
                        border: "1px solid #343741",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      labelStyle={{ color: "#f5f5f6" }}
                      formatter={(value) => [`${value}s`, "Lap time"]}
                      labelFormatter={(value) => `Lap ${value}`}
                    />
                    {chartDrivers.map((driver) => (
                      <Line
                        key={driver.code}
                        type="monotone"
                        dataKey={driver.code}
                        name={driver.code}
                        stroke={driver.color}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, strokeWidth: 0 }}
                        isAnimationActive={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>

              <div className="chart-foot">
                <span>
                  <span className="live-dot" />
                  {status === "live" ? "Historical API data" : "No data available"}
                </span>
                <span>Lap 01 — {lapLimit}</span>
              </div>
            </article>

            <article className="panel driver-panel">
              <PanelHeading
                kicker="CLASSIFICATION / 02"
                title="Driver pace"
                description="Average valid lap times"
                extra={<ArrowUpRight size={18} className="muted-icon" />}
              />

              <label className="search-box">
                <Search size={15} />
                <input
                  placeholder="Search driver or team..."
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
                {search && (
                  <button
                    className="clear-search"
                    onClick={() => setSearch("")}
                    aria-label="Clear search"
                  >
                    <X size={14} />
                  </button>
                )}
              </label>

              <div className="driver-list">
                {visibleDrivers.map((driver, index) => (
                  <button
                    className={`driver-row ${
                      selected.includes(driver.code) ? "driver-selected" : ""
                    }`}
                    key={driver.code}
                    onClick={() => toggleDriver(driver.code)}
                    aria-pressed={selected.includes(driver.code)}
                  >
                    <span className="driver-rank">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span
                      className="team-stripe"
                      style={{ background: driver.color }}
                    />
                    <span className="driver-info">
                      <strong>{driver.code}</strong>
                      <small>{driver.name}</small>
                    </span>
                      <span className="driver-time">
                        {driver.avg == null ? (["DNF", "DNS", "DSQ"].includes(driver.status) ? driver.status : "—") : driver.avg.toFixed(2)}{driver.avg == null || ["DNF", "DNS", "DSQ"].includes(driver.status) ? null : <small>s</small>}
                      </span>
                  </button>
                ))}
                {visibleDrivers.length === 0 && (
                  <div className="no-results">
                    No drivers match "{search}".
                    <button onClick={() => setSearch("")}>Clear search</button>
                  </div>
                )}
              </div>

              <div className="driver-footer">
                <span>{activeSelection.length} selected for chart</span>
                <button onClick={resetDrivers}>Reset</button>
              </div>
            </article>
          </section>

          <section className="bottom-grid">
            <article className="panel strategy-panel" id="tyre-strategy">
              <PanelHeading
                kicker="TYRE MANAGEMENT / 03"
                title="Tyre strategy"
                description={`Stint breakdown (first ${lapLimit} laps)`}
                extra={<Layers3 size={18} className="muted-icon" />}
              />

              {tyreStints.length > 0 ? (
                <div className="tyre-rows">
                  {drivers.map((driver) => {
                    const stints = tyreStints.filter((st) => st.driver_code === driver.code && st.start_lap != null && st.end_lap != null);
                    const total = stints.reduce((sum, st) => sum + Math.max(0, Number(st.end_lap) - Number(st.start_lap) + 1), 0);
                    if (!stints.length) return null;
                    return <div className="tyre-row" key={driver.code}>
                      <strong>{driver.code}</strong>
                      <div className="stint-track">
                        {stints.map((st) => {
                          const compound = String(st.compound || "unknown").toLowerCase();
                          const width = total ? (Math.max(0, Number(st.end_lap)-Number(st.start_lap)+1) / total) * 100 : 0;
                          return <span key={`${driver.code}-${st.stint_number}`} title={`${st.compound || "Unknown"}: laps ${st.start_lap}-${st.end_lap}`} className={`tyre ${compound}`} style={{width: `${width}%`}} />;
                        })}
                      </div>
                      <span className="tyre-label">{total} laps</span>
                    </div>;
                  })}
                </div>
              ) : <div className="empty-state"><div className="empty-icon"><Database size={21} /></div><strong>Tyre data unavailable</strong><span>Import OpenF1 stint records for this session.</span></div>}

              <div className="legend-note">
                <span className="legend-circle soft" /> Soft
                <span className="legend-circle medium" /> Medium
                <span className="legend-circle hard" /> Hard
                <span className="legend-circle intermediate" /> Inter
                <span className="legend-circle wet" /> Wet
              </div>
              <p className="footnote">Actual tyre stints from the selected historical session.</p>
            </article>

            <article className="panel pit-panel" id="pit-stops">
              <PanelHeading
                kicker="STRATEGY / 04"
                title="Pit stops"
                description="Pit-stop duration and timing"
                extra={<Timer size={18} className="muted-icon" />}
              />

              {pitStops.length > 0 ? (
                <div className="pit-table-wrap">
                  <table className="pit-table">
                    <thead>
                      <tr>
                        <th>Driver</th>
                        <th>Lap</th>
                        <th>Stop</th>
                        <th>Duration</th>
                        <th>Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pitStops.map((p, index) => (
                        <tr key={index}>
                          <td>{p.driver_code}</td>
                          <td>{p.lap_number}</td>
                          <td>{p.stop_number}</td>
                          <td>
                            {p.stop_duration_seconds != null
                              ? p.stop_duration_seconds.toFixed(1) + "s"
                              : "\u2014"}
                          </td>
                          <td>{formatTime(p.pit_timestamp)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-state">
                  <div className="empty-icon"><Database size={21} /></div>
                  <strong>Waiting for pit-stop data</strong>
                  <span>
                    Connect the backend to inspect pit timing and compare stop
                    durations between drivers.
                  </span>
                </div>
              )}
            </article>
          </section>

          <section className="panel events-panel" id="race-control">
            <PanelHeading
              kicker="RACE DIRECTOR / 05"
              title="Race control"
              description="Flags, incidents and official session messages"
              extra={<Radio size={18} className="muted-icon" />}
            />

            {raceControl.length > 0 ? (
              <div className="events-list">
                {raceControl.map((e, index) => (
                  <div key={index} className="event-row">
                    <span className="event-time">{formatTime(e.recorded_at)}</span>
                    <span className="event-driver">{e.driver_code || "\u2014"}</span>
                    <span className="event-lap">Lap {e.lap_number || "\u2014"}</span>
                    <span className="event-category">{e.category || "\u2014"}</span>
                    <span className="event-message">{e.message}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="events-empty">
                <div className="empty-icon"><Radio size={21} /></div>
                <div>
                  <strong>No race-control records for this session</strong>
                  <p>Import historical OpenF1 race-control messages to populate this panel.</p>
                </div>
              </div>
            )}
          </section>

          {status === "error" && (
            <div className="error-banner">
              API connection failed: {error}. Ensure the FastAPI backend is
              running on http://localhost:8000 and PostgreSQL is reachable.
            </div>
          )}

          <footer className="page-footer">
            <span>RAMP / RACE STRATEGY ANALYTICS</span>
            <span>Prototype \u00B7 Connected to FastAPI backend</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
