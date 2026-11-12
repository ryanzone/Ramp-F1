import { BarChart3 } from "lucide-react";
import AnalyticsChart from "./AnalyticsChart.jsx";

const CARDS = [
  { key: "pace", title: "Driver pace comparison", note: "Average clean lap per driver" },
  { key: "compare", title: "Lap-time comparison", note: "The two race leaders, lap by lap" },
  { key: "positions", title: "Driver position progression", note: "Top five, by lap" },
  { key: "stints", title: "Tyre stint visualization", note: "Compounds and stint lengths so far" },
  { key: "pits", title: "Pit-stop comparison", note: "Stops completed per driver" },
  { key: "tyres", title: "Tyre strategy distribution", note: "Compounds on track right now" },
];

export default function VisualAnalytics({ replay, analytics, colors }) {
  const { charts, chartsLoading } = analytics;
  const lap = replay.server?.current_lap ?? 0;
  return (
    <section className="panel visual-panel" id="visual-analytics">
      <div className="panel-heading">
        <div>
          <div className="panel-kicker">VISUAL ANALYTICS / 07</div>
          <h2>Charts from live SQL</h2>
          <p>Every chart is a SQL query re-run each lap. It only contains what is known at lap {lap}.</p>
        </div>
        <BarChart3 size={18} className="muted-icon" />
      </div>

      {!replay.active ? (
        <div className="empty-state">
          <div className="empty-icon"><BarChart3 size={21} /></div>
          <strong>Start a replay to generate charts</strong>
          <span>Charts are built from SQL results and update as the replay clock advances.</span>
        </div>
      ) : (
        <div className="chart-grid">
          {CARDS.map((card) => {
            const result = charts[card.key];
            return (
              <article className="chart-card" key={card.key}>
                <header>
                  <div>
                    <h3>{card.title}</h3>
                    <small>{result && result.title ? result.title : card.note}</small>
                  </div>
                  <span className="lap-tag">LAP {result?.current_lap ?? lap}</span>
                </header>
                <div className="chart-box">
                  {!result ? (
                    <div className="chart-empty">{chartsLoading ? "Running query…" : "Waiting for the first lap."}</div>
                  ) : result.status === "error" ? (
                    <div className="chart-empty error">{result.answer}</div>
                  ) : result.status === "needs_clarification" || result.status === "unsupported" ? (
                    <div className="chart-empty">{result.answer}</div>
                  ) : result.row_count === 0 ? (
                    <div className="chart-empty">No data yet at this point of the replay.</div>
                  ) : (
                    <AnalyticsChart result={result} colors={colors} />
                  )}
                </div>
                {result && result.sql && (
                  <details>
                    <summary>SQL · {result.elapsed_ms} ms · {result.row_count} rows</summary>
                    <pre><code>{result.sql}</code></pre>
                  </details>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
