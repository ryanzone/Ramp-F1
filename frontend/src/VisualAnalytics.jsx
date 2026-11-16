import { BarChart3, Code2 } from "lucide-react";
import AnalyticsChart from "./AnalyticsChart.jsx";

const CARDS = [
  { key: "pace", title: "Driver pace comparison", note: "Average clean lap per driver" },
  { key: "compare", title: "Lap-time comparison", note: "The two race leaders, lap by lap" },
  { key: "positions", title: "Driver position progression", note: "Top five, by lap" },
];

export default function VisualAnalytics({ replay, analytics, colors }) {
  const { charts, chartsLoading } = analytics;
  const lap = replay.server?.current_lap ?? 0;
  const finished = replay.server?.finished === true;

  return (
    <section className="panel visual-panel" id="visual-analytics">
      <div className="panel-heading">
        <div>
          <div className="panel-kicker">VISUAL ANALYTICS / 07</div>
          <h2>Complete Race Analytics</h2>
          <p>
            Full-race SQL analysis across all completed laps.
            {finished ? ` Final lap: ${lap}.` : ` Current lap: ${lap}.`}
          </p>
        </div>

        <div className="visual-panel-badge">
          <BarChart3 size={16} className="muted-icon" />
          <span>{finished ? "FINAL" : `LAP ${lap}`}</span>
        </div>
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
            const cardLap = result?.current_lap ?? lap;
            const isWide = card.key === "positions";

            return (
              <article className={`chart-card ${isWide ? "is-wide" : ""}`} key={card.key}>
                <header>
                  <div className="chart-card-title">
                    <h3>{card.title}</h3>
                    <small>{result && result.title ? result.title : card.note}</small>
                  </div>
                  <span className={`lap-tag ${finished ? "is-final" : ""}`}>
                    {finished ? "FINAL" : `LAP ${cardLap}`}
                  </span>
                </header>

                <div className={`chart-box ${isWide ? "is-tall" : ""}`}>
                  {!result ? (
                    <div className="chart-empty">
                      {chartsLoading && <span className="chart-spinner" />}
                      <span>{chartsLoading ? "Running query…" : "Waiting for the first lap."}</span>
                    </div>
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
                  <details className="chart-sql">
                    <summary>
                      <span className="chart-sql-label">
                        <Code2 size={13} />
                        <span>View SQL</span>
                      </span>
                      <span className="chart-sql-meta">
                        {result.row_count} rows · {result.elapsed_ms} ms
                      </span>
                    </summary>
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