import { usePostRaceAnalysis } from "./usePostRaceAnalysis.js";
import AnalyticsChart from "./AnalyticsChart.jsx";

const CHARTS = [
  {
    key: "pace",
    title: "Race Pace",
    description: "Average clean lap time across the grid.",
  },
  {
    key: "stints",
    title: "Tyre Strategy",
    description: "Tyre compounds and stint lengths for each driver.",
  },
  {
    key: "positions",
    title: "Position Progression",
    description: "How every driver's position changed throughout the race.",
  },
];

export default function PostRaceAnalysis({ replay }) {
  const { data, loading, error } = usePostRaceAnalysis(
    replay.replayId,
    replay.server?.finished === true
  );

  const totalLaps =
    data?.total_laps ??
    replay.server?.total_laps ??
    replay.server?.current_lap ??
    0;

  const driverCount = data?.charts?.pace?.row_count ?? 0;

  const statusState = loading
    ? "is-loading"
    : error
      ? "is-error"
      : "is-ready";

  return (
    <main className="postrace-screen" data-hit>
      <div className="postrace-container">
        <header className="postrace-heading">
          <div className="postrace-title-block">
            <span className="postrace-kicker">RAMP / RACE COMPLETE</span>
            <h1>Post-Race Analysis</h1>
            <p>The race is over. Here's the complete breakdown.</p>
          </div>

          <span className={`postrace-status ${statusState}`}>
            <span className="status-dot" />
            {loading
              ? "BUILDING ANALYSIS"
              : error
                ? "ANALYSIS ERROR"
                : "RACE COMPLETE"}
          </span>
        </header>

        {!error && !loading && data && (
          <section className="postrace-stats" aria-label="Race summary metrics">
            <article className="postrace-stat">
              <span>COMPLETED LAPS</span>
              <strong>{String(totalLaps).padStart(2, "0")}</strong>
            </article>

            <article className="postrace-stat">
              <span>DRIVERS ANALYSED</span>
              <strong>{String(driverCount).padStart(2, "0")}</strong>
            </article>

            <article className="postrace-stat">
              <span>ANALYSIS AREAS</span>
              <strong>03</strong>
            </article>
          </section>
        )}

        {error && (
          <div className="postrace-message error" role="alert">
            {error}
          </div>
        )}

        {loading && (
          <section className="postrace-loading" aria-busy="true">
            <div className="postrace-message">
              <span className="postrace-spinner" />
              Loading full-race analysis...
            </div>
            <div className="postrace-skeleton-grid">
              <div className="postrace-skeleton-card" />
              <div className="postrace-skeleton-card" />
              <div className="postrace-skeleton-card wide" />
            </div>
          </section>
        )}

        {!loading && !error && data && (
          <section className="postrace-chart-list">
            {CHARTS.map((chart) => {
              const result = data.charts?.[chart.key];

              return (
                <article
                  className={`postrace-chart-card ${
                    chart.key === "positions" ? "positions-card" : ""
                  }`}
                  key={chart.key}
                >
                  <header>
                    <div>
                      <h2>{chart.title}</h2>
                      <p>{chart.description}</p>
                    </div>

                    <span className="postrace-chart-count">
                      {result?.row_count ?? 0} RECORDS
                    </span>
                  </header>

                  <div
                    className={`postrace-chart-box ${
                      chart.key === "positions" ? "positions-chart" : ""
                    }`}
                  >
                    {!result ? (
                      <div className="chart-empty">No result returned.</div>
                    ) : result.status !== "ok" ? (
                      <div className="chart-empty error">
                        {result.answer || "Query failed."}
                      </div>
                    ) : result.row_count === 0 ? (
                      <div className="chart-empty">
                        No recorded data available.
                      </div>
                    ) : (
                      <AnalyticsChart result={result} />
                    )}
                  </div>
                </article>
              );
            })}
          </section>
        )}
      </div>
    </main>
  );
}