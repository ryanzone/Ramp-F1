import { useEffect, useRef, useState } from "react";
import { ArrowUp, Sparkles } from "lucide-react";

const STARTERS = [
  "Who is leading?",
  "Who has the best race pace?",
  "Which drivers have not pitted yet?",
  "Who has been penalised?",
];

// Context-aware next questions, so follow-ups feel like a conversation.
const FOLLOW_UPS = {
  fastest_avg: ["Compare him with the second-fastest", "Who has the highest tyre degradation?"],
  recent_pace: ["Compare him with the second-fastest", "Which driver has been most consistent?"],
  standings: ["Who gained the most positions?", "Identify potential overtake opportunities"],
  penalties_list: ["Show the standings", "What is the race status?"],
  penalty_reason: ["Who has been penalised?", "How is he doing?"],
  compare_drivers: ["Which drivers could benefit from an undercut?", "Who has the highest tyre degradation?"],
  tyres_now: ["Who has the highest tyre degradation?", "Compare tyre strategies between constructors"],
  not_pitted: ["Which team has the fastest average pit stops?", "Which drivers could benefit from an undercut?"],
  pit_team_avg: ["How many pit stops has each driver completed?", "Analyse the time lost during pit stops"],
};
const DEFAULT_FOLLOW_UPS = ["Show the standings", "What happened in the last 10 minutes?"];

export default function PitWall({ replay, analytics, onShowSql }) {
  const { messages, busy, stage, ask } = analytics;
  const [text, setText] = useState("");
  const thread = useRef(null);
  const last = [...messages].reverse().find((m) => m.role === "analyst");

  // Scroll only the chat itself; scrollIntoView would drag the whole page to the Pit Wall.
  useEffect(() => {
    if (thread.current) thread.current.scrollTop = thread.current.scrollHeight;
  }, [messages.length, busy]);

  const submit = (event) => {
    event.preventDefault();
    if (!text.trim()) return;
    ask(text);
    setText("");
  };
  const suggestions = last
    ? FOLLOW_UPS[last.result.intent] || DEFAULT_FOLLOW_UPS
    : STARTERS;

  return (
    <aside className="glass pitwall" aria-label="Pit Wall analyst">
      <header>
        <span className="pw-title"><Sparkles size={14} /> PIT WALL</span>
        <span className="pw-tag">SQL ANALYST</span>
      </header>

      {!replay.active ? (
        <div className="pw-empty">
          <h3>Ask the race.</h3>
          <p>Start a replay to ask questions. Every answer is a real SQL query over the data up to the replay clock.</p>
        </div>
      ) : (
        <>
          <div className="pw-thread" ref={thread}>
            {messages.length === 0 && (
              <div className="pw-empty">
                <h3>The race, explained.</h3>
                <p>Ask about pace, tyres, pit stops, gaps, penalties and more. Try a question below.</p>
              </div>
            )}
            {messages.map((m) => {
              if (m.role === "user") {
                return (
                  <div className="pw-bubble user" key={m.id}>
                    <small>YOU ASKED</small>
                    <p>{m.text}</p>
                  </div>
                );
              }
              if (m.role === "error") {
                return (
                  <div className="pw-bubble error" key={m.id}>
                    <small>COULD NOT ANSWER</small>
                    <p>{m.text}</p>
                  </div>
                );
              }
              const r = m.result;
              return (
                <div className={`pw-bubble analyst ${r.status !== "ok" ? "soft" : ""}`} key={m.id}>
                  <small><Sparkles size={11} /> {r.status === "ok" ? "RAMP INSIGHT" : r.status === "unsupported" ? "NOT SUPPORTED YET" : "ONE QUESTION"}
                    <em>LAP {r.current_lap}</em></small>
                  <p>{r.answer}</p>
                  {r.note && <p className="pw-note">{r.note}</p>}
                  {r.sql && (
                    <div className="pw-meta">
                      <span>{r.title}</span>
                      <span>{r.row_count} rows · {r.elapsed_ms} ms{r.cached ? " · cached" : ""}</span>
                      <button type="button" onClick={() => onShowSql(r.id)}>View SQL</button>
                    </div>
                  )}
                  {r.used_context?.length > 0 && <p className="pw-context">Used context: {r.used_context.join("; ")}</p>}
                </div>
              );
            })}
            {busy && <div className="pw-status" role="status">{stage || "working"}…</div>}
          </div>

          <div className="pw-chips">
            {suggestions.map((s) => (
              <button type="button" key={s} disabled={busy} onClick={() => ask(s)}>{s}</button>
            ))}
          </div>
        </>
      )}

      <form className="pw-input" onSubmit={submit}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={replay.active ? "Ask about this race…" : "Start a replay first"}
          disabled={!replay.active}
          maxLength={500}
          aria-label="Question for the Pit Wall"
        />
        <button type="submit" disabled={!replay.active || busy || !text.trim()} aria-label="Send question"><ArrowUp size={16} /></button>
      </form>
      <p className="pw-foot">Answers come from SQL over data up to the replay clock. No AI model, no guessing.</p>
    </aside>
  );
}
