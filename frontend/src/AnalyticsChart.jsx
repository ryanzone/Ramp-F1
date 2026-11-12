import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { compoundInfo, teamColor } from "./replayModel.js";

const GRID = "#292c34";
const AXIS = { fill: "#858a97", fontSize: 11 };
const TOOLTIP = {
  contentStyle: { background: "#17191f", border: "1px solid #343741", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "#f5f5f6" },
};
const SERIES = ["#c6f35a", "#ff914d", "#4788ef", "#bd7aff", "#ffd166", "#49d7cb"];

function toObjects(result) {
  return (result.rows || []).map((row) => Object.fromEntries(result.columns.map((c, i) => [c, row[i]])));
}

function Empty({ text = "No data yet at this point of the replay." }) {
  return <div className="chart-empty">{text}</div>;
}

function BarView({ data, hint }) {
  const key = hint.y[0];
  const colored = data.some((d) => d.team_name);
  const whole = data.every((d) => d[key] == null || Number.isInteger(d[key]));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 5" vertical={false} />
        <XAxis dataKey={hint.x} tick={AXIS} tickLine={false} axisLine={false} interval={0} angle={data.length > 10 ? -45 : 0} height={data.length > 10 ? 46 : 24} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} domain={["auto", "auto"]} allowDecimals={!whole} />
        <Tooltip {...TOOLTIP} cursor={{ fill: "rgba(255,255,255,.04)" }} />
        <Bar dataKey={key} radius={[3, 3, 0, 0]} isAnimationActive={false}>
          {data.map((d, i) => (
            <Cell key={i} fill={colored ? teamColor(d.team_name) : SERIES[0]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// Pit-in/out and safety-car laps are far slower than the rest and would flatten the real
// differences, so the axis follows the typical laps (median + 12%); outliers run off the top.
function typicalDomain(data, keys) {
  const values = data.flatMap((d) => keys.map((k) => d[k])).filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (values.length < 6) return ["dataMin - 0.5", "dataMax + 0.5"];
  const median = values[Math.floor(values.length / 2)];
  return [Math.floor(values[0] - 0.5), Math.ceil(median * 1.12)];
}

function LineView({ data, hint }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 8, right: 12, left: -14, bottom: 0 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 5" vertical={false} />
        <XAxis dataKey={hint.x} tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} domain={typicalDomain(data, hint.y)} allowDataOverflow tickFormatter={(v) => v.toFixed(0)} />
        <Tooltip {...TOOLTIP} labelFormatter={(v) => `Lap ${v}`} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {hint.y.map((k, i) => (
          <Line key={k} type="monotone" dataKey={k} name={(hint.labels || {})[k] || k} stroke={SERIES[i % SERIES.length]}
            strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

function PositionView({ data, hint, colors }) {
  const codes = [...new Set(data.map((d) => d[hint.series]))];
  const byLap = {};
  data.forEach((d) => {
    byLap[d[hint.x]] = byLap[d[hint.x]] || { [hint.x]: d[hint.x] };
    byLap[d[hint.x]][d[hint.series]] = d[hint.y];
  });
  const wide = Object.values(byLap).sort((a, b) => a[hint.x] - b[hint.x]);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={wide} margin={{ top: 8, right: 12, left: -14, bottom: 0 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 5" vertical={false} />
        <XAxis dataKey={hint.x} tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis reversed domain={[1, "dataMax"]} allowDecimals={false} tick={AXIS} tickLine={false} axisLine={false} />
        <Tooltip {...TOOLTIP} labelFormatter={(v) => `Lap ${v}`} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {codes.map((c, i) => (
          <Line key={c} type="monotone" dataKey={c} stroke={(colors && colors[c]) || SERIES[i % SERIES.length]}
            strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

function CompoundView({ data, hint }) {
  const counts = {};
  data.forEach((d) => {
    const k = String(d[hint.group] || "UNKNOWN").toUpperCase();
    counts[k] = (counts[k] || 0) + 1;
  });
  const slices = Object.entries(counts).map(([name, value]) => ({ name: compoundInfo(name).label, value, color: compoundInfo(name).color }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie data={slices} dataKey="value" nameKey="name" innerRadius="48%" outerRadius="78%" paddingAngle={2} stroke="none" isAnimationActive={false}
          label={({ name, value }) => `${name} ${value}`}>
          {slices.map((s) => (
            <Cell key={s.name} fill={s.color} />
          ))}
        </Pie>
        <Tooltip {...TOOLTIP} />
      </PieChart>
    </ResponsiveContainer>
  );
}

function StintView({ data }) {
  const maxLap = Math.max(1, ...data.map((d) => d.last_lap || 0));
  const drivers = [...new Set(data.map((d) => d.driver_code))];
  return (
    <div className="stint-chart">
      {drivers.map((code) => (
        <div className="stint-chart-row" key={code}>
          <strong>{code}</strong>
          <div className="stint-track">
            {data.filter((d) => d.driver_code === code).sort((a, b) => a.stint_number - b.stint_number).map((d) => {
              const span = Math.max(1, d.last_lap - d.start_lap + 1);
              return (
                <span key={d.stint_number} className="stint-seg" style={{ width: `${(span / maxLap) * 100}%`, background: compoundInfo(d.compound).color }}
                  title={`${compoundInfo(d.compound).label}: laps ${d.start_lap}-${d.last_lap}${d.status === "running" ? " (running)" : ""}`} />
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AnalyticsChart({ result, colors }) {
  if (!result || !result.chart || result.status !== "ok") return null;
  const hint = result.chart;
  const data = toObjects(result);
  if (hint.type === "table") return null;
  if (!data.length) return <Empty />;
  switch (hint.type) {
    case "bar":
      return <BarView data={data} hint={hint} />;
    case "line":
      return <LineView data={data} hint={hint} />;
    case "position_lines":
      return <PositionView data={data} hint={hint} colors={colors} />;
    case "tyre_distribution":
      return <CompoundView data={data} hint={hint} />;
    case "tyre_stints":
      return <StintView data={data} />;
    default:
      return null;
  }
}
