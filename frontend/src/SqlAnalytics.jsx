import { useState } from "react";
import { Copy, Database, Search } from "lucide-react";
import AnalyticsChart from "./AnalyticsChart.jsx";

const STAGES = ["parsing", "validating", "executing", "explaining"];
const MAX_ROWS = 100;

function cell(value) {
  if (value == null) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

function StatusBadge({ result }) {
  if (result.status !== "ok") {
    return <span className="badge warn">{result.status === "unsupported" ? "NOT SUPPORTED" : "NEEDS DETAIL"}</span>;
  }
  return <span className="badge ok">{result.cached ? "OK · CACHED" : "OK"}</span>;
}

function ResultView({ result, colors }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(result.sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard unavailable */
    }
  };
  const params = Object.entries(result.params || {});
  return (
    <div className="sql-result">
      <div className="sql-badges">
        <StatusBadge result={result} />
        <span>{result.elapsed_ms} ms</span>
        <span>{result.row_count} rows{result.truncated ? " (truncated)" : ""}</span>
        <span>lap {result.current_lap}</span>
        <span>replay time {result.replay_time.slice(11, 19)}</span>
      </div>
      <p className="sql-answer">{result.answer}</p>
      {result.note && <p className="sql-note">{result.note}</p>}

      {result.sql ? (
        <>
          <div className="sql-box">
            <div className="sql-box-head">
              <span>GENERATED SQL</span>
              <button type="button" onClick={copy}><Copy size={12} /> {copied ? "Copied" : "Copy"}</button>
            </div>
            <pre><code>{result.sql}</code></pre>
            {params.length > 0 && (
              <div className="sql-params">
                {params.map(([k, v]) => (
                  <span key={k}><b>:{k}</b> = {String(v)}</span>
                ))}
              </div>
            )}
          </div>

          <div className="sql-how">
            <div className="sql-chips">
              {(result.features || []).map((f) => (
                <span key={f}>{f}</span>
              ))}
              {(result.tables || []).map((t) => (
                <span className="table" key={t}>replay.{t}</span>
              ))}
            </div>
            <p>{result.how}</p>
            <p className="boundary">{result.time_boundary}</p>
          </div>

          {result.chart && result.chart.type !== "table" && result.row_count > 0 && (
            <div className="sql-chart">
              <AnalyticsChart result={result} colors={colors} />
            </div>
          )}

          {result.row_count > 0 ? (
            <div className="sql-table-wrap">
              <table>
                <thead>
                  <tr>{result.columns.map((c) => <th key={c}>{c}</th>)}</tr>
                </thead>
                <tbody>
                  {result.rows.slice(0, MAX_ROWS).map((row, i) => (
                    <tr key={i}>{row.map((v, j) => <td key={j} className={typeof v === "number" ? "num" : ""}>{cell(v)}</td>)}</tr>
                  ))}
                </tbody>
              </table>
              {result.rows.length > MAX_ROWS && <p className="foot-note">Showing the first {MAX_ROWS} of {result.rows.length} rows.</p>}
            </div>
          ) : (
            <p className="foot-note">The query ran and returned no rows at this point of the replay.</p>
          )}
        </>
      ) : (
        result.suggestions?.length > 0 && (
          <div className="sql-chips">
            {result.suggestions.slice(0, 6).map((s) => <span key={s}>{s}</span>)}
          </div>
        )
      )}
    </div>
  );
}

export default function SqlAnalytics({ replay, analytics, colors }) {
  const { messages, busy, stage, ask, select, selected, selectedId } = analytics;
  const [text, setText] = useState("");
  const analystMessages = messages.filter((m) => m.role === "analyst");
  const errors = messages.filter((m) => m.role === "error");
  const lastError = errors.length && messages[messages.length - 1].role === "error" ? errors[errors.length - 1] : null;
  const shown = selected || (analystMessages.length ? analystMessages[analystMessages.length - 1].result : null);

  const submit = (event) => {
    event.preventDefault();
    if (!text.trim()) return;
    ask(text);
    setText("");
  };

  return (
    <section className="panel sql-panel" id="sql-analytics">
      <div className="panel-heading">
        <div>
          <div className="panel-kicker">SQL ANALYTICS / 06</div>
          <h2>Ask in plain English, get real SQL</h2>
          <p>Each question becomes a validated SELECT over views that only contain what is known at the replay clock.</p>
        </div>
        <Database size={18} className="muted-icon" />
      </div>

      <form className="sql-ask" onSubmit={submit}>
        <label className="search-box">
          <Search size={15} />
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={replay.active ? "e.g. Who gained the most positions?" : "Start a replay to ask questions"}
            disabled={!replay.active || busy}
            maxLength={500}
            aria-label="Question"
          />
        </label>
        <button type="submit" className="btn-accent" disabled={!replay.active || busy || !text.trim()}>Run query</button>
      </form>

      {busy && (
        <div className="sql-stages" role="status" aria-label="Query status">
          {STAGES.map((s) => (
            <span key={s} className={s === stage ? "now" : STAGES.indexOf(s) < STAGES.indexOf(stage) ? "done" : ""}>{s}</span>
          ))}
        </div>
      )}
      {lastError && <div className="inline-error" role="alert">{lastError.text}</div>}

      <div className="sql-layout">
        <div className="sql-history">
          <h3>History</h3>
          {analystMessages.length === 0 && <p className="foot-note">Questions you ask appear here.</p>}
          {[...analystMessages].reverse().map((m) => (
            <button type="button" key={m.id} className={m.id === (selectedId ?? shown?.id) ? "on" : ""} onClick={() => select(m.id)}>
              <span>{m.result.question}</span>
              <small>{m.result.status === "ok" ? `${m.result.title} · ${m.result.row_count} rows` : m.result.status.replace("_", " ")} · lap {m.result.current_lap}</small>
            </button>
          ))}
        </div>
        <div className="sql-detail">
          {shown ? <ResultView result={shown} colors={colors} /> : (
            <div className="empty-state">
              <div className="empty-icon"><Database size={21} /></div>
              <strong>No query yet</strong>
              <span>Ask a question to see the SQL that answers it, the rows it returned, and how long it took.</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
