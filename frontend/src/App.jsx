
import { useMemo, useState } from "react";
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
import "./index.css";

const drivers = [
  { code: "VER", name: "Max Verstappen", team: "Red Bull", color: "#4788ef", avg: 89.42 },
  { code: "NOR", name: "Lando Norris", team: "McLaren", color: "#ff914d", avg: 89.61 },
  { code: "LEC", name: "Charles Leclerc", team: "Ferrari", color: "#ff4d62", avg: 89.83 },
  { code: "HAM", name: "Lewis Hamilton", team: "Ferrari", color: "#bd7aff", avg: 90.04 },
  { code: "PIA", name: "Oscar Piastri", team: "McLaren", color: "#ffd166", avg: 89.76 },
  { code: "RUS", name: "George Russell", team: "Mercedes", color: "#49d7cb", avg: 90.12 },
];

const lapData = Array.from({ length: 20 }, (_, i) => ({
  lap: i + 1,
  VER: +(89.4 + Math.sin(i * 0.7) * 0.9 + i * 0.035).toFixed(2),
  NOR: +(89.6 + Math.cos(i * 0.55) * 0.8 + i * 0.025).toFixed(2),
  LEC: +(89.8 + Math.sin(i * 0.48 + 1) * 0.75 + i * 0.04).toFixed(2),
  HAM: +(90.0 + Math.cos(i * 0.52 + 1) * 0.8 + i * 0.03).toFixed(2),
  PIA: +(89.7 + Math.sin(i * 0.4 + 2) * 0.65 + i * 0.035).toFixed(2),
  RUS: +(90.1 + Math.cos(i * 0.45 + 2) * 0.7 + i * 0.025).toFixed(2),
}));

const navItems = [
  { name: "Overview", icon: Gauge, target: "overview" },
  { name: "Lap analysis", icon: Activity, target: "lap-analysis" },
  { name: "Tyre strategy", icon: Layers3, target: "tyre-strategy" },
  { name: "Pit stops", icon: Timer, target: "pit-stops" },
  { name: "Race control", icon: Radio, target: "race-control" },
];

const tyreStints = [
  { code: "VER", stints: [{ type: "medium", width: 38 }, { type: "hard", width: 62 }], plan: "M → H" },
  { code: "NOR", stints: [{ type: "hard", width: 55 }, { type: "medium", width: 45 }], plan: "H → M" },
  { code: "LEC", stints: [{ type: "medium", width: 48 }, { type: "hard", width: 52 }], plan: "M → H" },
  { code: "HAM", stints: [{ type: "hard", width: 45 }, { type: "medium", width: 55 }], plan: "H → M" },
];

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
  const [active, setActive] = useState("Overview");
  const [selected, setSelected] = useState(["VER", "NOR", "LEC"]);
  const [search, setSearch] = useState("");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [sessionOpen, setSessionOpen] = useState(false);
  const [session, setSession] = useState("Abu Dhabi Grand Prix");
  const [lapLimit, setLapLimit] = useState("20");

  const visibleDrivers = useMemo(
    () =>
      drivers.filter((driver) =>
        `${driver.code} ${driver.name} ${driver.team}`
          .toLowerCase()
          .includes(search.toLowerCase())
      ),
    [search]
  );

  const chartDrivers = drivers.filter((driver) =>
    selected.includes(driver.code)
  );

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
    setSelected(["VER", "NOR", "LEC"]);
    setSearch("");
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
          {navItems.map(({ name, icon: Icon, target }) => (
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
              <span /> DEMO DATA
            </span>
          </div>
        </header>

        <div className="page-content">
          <section className="page-heading" id="overview">
            <div>
              <div className="eyebrow">
                <Flag size={13} />
                2025 SEASON / RACE ANALYTICS
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
                  {["Abu Dhabi Grand Prix", "Select a session later"].map((item) => (
                    <button
                      key={item}
                      onClick={() => {
                        setSession(item);
                        setSessionOpen(false);
                      }}
                    >
                      {item}
                      {session === item && <span>✓</span>}
                    </button>
                  ))}
                  <p>Session selection is a UI preview until API integration.</p>
                </div>
              )}
            </div>
          </section>

          <section className="stats-grid">
            <StatCard
              icon={Flag}
              label="Race distance"
              value="58 laps"
              note="Yas Marina Circuit"
            />
            <StatCard
              icon={Activity}
              label="Drivers tracked"
              value="20"
              note="Full race field"
            />
            <StatCard
              icon={Timer}
              label="Pit stops"
              value="—"
              note="Database connection pending"
            />
            <StatCard
              icon={Gauge}
              label="Track temperature"
              value="— °C"
              note="Weather data pending"
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
                    data={lapData.slice(0, Number(lapLimit))}
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
                <span><span className="live-dot" /> Illustrative sample data</span>
                <span>Lap 01 — {lapLimit}</span>
              </div>
            </article>

            <article className="panel driver-panel">
              <PanelHeading
                kicker="CLASSIFICATION / 02"
                title="Driver pace"
                description="Illustrative average lap times"
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
                      {driver.avg.toFixed(2)}<small>s</small>
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
                <span>{selected.length} selected for chart</span>
                <button onClick={resetDrivers}>Reset</button>
              </div>
            </article>
          </section>

          <section className="bottom-grid">
            <article className="panel strategy-panel" id="tyre-strategy">
              <PanelHeading
                kicker="TYRE MANAGEMENT / 03"
                title="Tyre strategy"
                description="Illustrative stint breakdown"
                extra={<Layers3 size={18} className="muted-icon" />}
              />

              <div className="tyre-rows">
                {tyreStints.map((driver) => (
                  <div className="tyre-row" key={driver.code}>
                    <strong>{driver.code}</strong>
                    <div className="stint-track">
                      {driver.stints.map((stint, index) => (
                        <span
                          key={`${driver.code}-${index}`}
                          className={`tyre ${stint.type}`}
                          style={{ width: `${stint.width}%` }}
                        />
                      ))}
                    </div>
                    <span className="tyre-label">{driver.plan}</span>
                  </div>
                ))}
              </div>

              <div className="legend-note">
                <span className="legend-circle medium" /> Medium
                <span className="legend-circle hard" /> Hard
              </div>
              <p className="footnote">
                Sample strategies only. Actual stint data not connected yet.
              </p>
            </article>

            <article className="panel pit-panel" id="pit-stops">
              <PanelHeading
                kicker="STRATEGY / 04"
                title="Pit stops"
                description="Pit-stop duration and timing"
                extra={<Timer size={18} className="muted-icon" />}
              />

              <div className="empty-state">
                <div className="empty-icon"><Database size={21} /></div>
                <strong>Waiting for pit-stop data</strong>
                <span>
                  Connect the backend to inspect pit timing and compare stop
                  durations between drivers.
                </span>
              </div>
            </article>
          </section>

          <section className="panel events-panel" id="race-control">
            <PanelHeading
              kicker="RACE DIRECTOR / 05"
              title="Race control"
              description="Flags, incidents and official session messages"
              extra={<Radio size={18} className="muted-icon" />}
            />

            <div className="events-empty">
              <div className="empty-icon"><Radio size={21} /></div>
              <div>
                <strong>No connected race-control events</strong>
                <p>
                  Historical messages will appear here after the database
                  endpoint is connected.
                </p>
              </div>
            </div>
          </section>

          <footer className="page-footer">
            <span>RAMP / RACE STRATEGY ANALYTICS</span>
            <span>Prototype · Historical data integration pending</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
