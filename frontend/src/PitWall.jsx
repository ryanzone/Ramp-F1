import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, ChevronDown, Sparkles } from "lucide-react";

const QUESTION_GROUPS = [
  {
    title: "Race pace",
    questions: [
      "Who is leading?",
      "Who has the best race pace?",
      "Which driver has the strongest pace over the last five laps?",
      "Which driver has been most consistent?",
      "Who had the fastest lap?",
      "Identify drivers losing significant time",
    ],
  },
  {
    title: "Tyres & strategy",
    questions: [
      "Which drivers have not pitted yet?",
      "Who has the highest tyre degradation?",
      "Compare tyre strategies between constructors",
      "Which drivers could benefit from an undercut?",
      "Which drivers are currently running on hard tyres?",
      "Show the tyre stints",
    ],
  },
  {
    title: "Pit stops",
    questions: [
      "Which team has the fastest average pit stops?",
      "How many pit stops has each driver completed?",
      "Analyse the time lost during pit stops",
      "Which driver lost the most time in the pits?",
    ],
  },
  {
    title: "Positions & standings",
    questions: [
      "Show the standings",
      "Who gained the most positions?",
      "Who lost the most positions?",
      "Show the position changes",
      "Identify potential overtake opportunities",
    ],
  },
  {
    title: "Incidents & penalties",
    questions: [
      "Who has been penalised?",
      "Why was the driver penalised?",
      "What is the race status?",
      "What happened in the last 10 minutes?",
    ],
  },
];

const POST_RACE_GROUPS = [
  {
    title: "Race review",
    questions: [
      "Show the final standings",
      "Who had the fastest lap?",
      "Who gained the most positions?",
      "Who lost the most positions?",
    ],
  },
  {
    title: "Pace analysis",
    questions: [
      "Who has the best race pace?",
      "Rank the drivers by consistency",
      "Which driver has the strongest pace over the last five laps?",
    ],
  },
  {
    title: "Tyres & pit strategy",
    questions: [
      "Show the tyre stints",
      "Compare tyre strategies between constructors",
      "Which team has the fastest average pit stops?",
      "How many pit stops has each driver completed?",
      "Which driver lost the most time in the pits?",
    ],
  },
  {
    title: "Positions & incidents",
    questions: [
      "Analyse position changes throughout the race",
      "Who has been penalised?",
      "What is the race status?",
      "What happened in the last 10 minutes?",
    ],
  },
];

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
const DEFAULT_FOLLOW_UPS = ["Show the standings", "Who has the best race pace?"];

export default function PitWall({ replay, analytics, onShowSql }) {
  const { messages, busy, stage, ask } = analytics;
  const [text, setText] = useState("");
  const [showQuestionBank, setShowQuestionBank] = useState(false);
  const finished = replay.server?.finished === true;
  const groups = finished ? POST_RACE_GROUPS : QUESTION_GROUPS;
  // Which question group is open; resets when the race finishes (adjusted during render, not in an effect).
  const [groupState, setGroupState] = useState({ finished, open: groups[0].title });
  if (groupState.finished !== finished) setGroupState({ finished, open: groups[0].title });
  const openGroup = groupState.open;
  const setOpenGroup = (next) => setGroupState((s) => ({ ...s, open: typeof next === "function" ? next(s.open) : next }));
  const thread = useRef(null);
  const last = [...messages].reverse().find((m) => m.role === "analyst");

  useEffect(() => {
    if (thread.current) thread.current.scrollTop = thread.current.scrollHeight;
  }, [messages.length, busy]);

  const submit = (event) => {
    event.preventDefault();
    if (!text.trim()) return;
    ask(text.trim());
    setText("");
  };

  const suggestions = useMemo(() => {
    if (last) return FOLLOW_UPS[last.result.intent] || DEFAULT_FOLLOW_UPS;
    return finished
      ? ["Show the final standings", "Show the tyre stints", "Who had the fastest lap?"]
      : ["Who is leading?", "Who has the best race pace?", "Which drivers have not pitted yet?"];
  }, [last, finished]);

  const askQuestion = (question) => {
    if (busy) return;
    ask(question);
    setShowQuestionBank(false);
  };

  return (
    <aside className="glass pitwall" aria-label="Pit Wall analyst">
      <header>
        <span className="pw-title"><Sparkles size={14} /> PIT WALL</span>
        <span className="pw-tag">{finished ? "POST-RACE" : "SQL ANALYST"}</span>
      </header>

      {!replay.active ? (
        <div className="pw-empty">
          <h3>Ask the race.</h3>
          <p>Start a replay to ask questions. Answers are based on race data available to the analyst.</p>
        </div>
      ) : (
        <>
          <div className="pw-thread" ref={thread}>
            {messages.length === 0 && (
              <div className="pw-empty">
                <h3>{finished ? "The race, reviewed." : "The race, explained."}</h3>
                <p>{finished
                  ? "Explore the race result, driver pace, tyre strategy, pit stops and incidents."
                  : "Ask about pace, tyres, pit stops, gaps, penalties and more. Choose a question or type your own."}</p>
              </div>
            )}
            {messages.map((m) => {
              if (m.role === "user") {
                return <div className="pw-bubble user" key={m.id}><small>YOU ASKED</small><p>{m.text}</p></div>;
              }
              if (m.role === "error") {
                return <div className="pw-bubble error" key={m.id}><small>COULD NOT ANSWER</small><p>{m.text}</p></div>;
              }
              const r = m.result;
              return (
                <div className={`pw-bubble analyst ${r.status !== "ok" ? "soft" : ""}`} key={m.id}>
                  <small>
                    <Sparkles size={11} /> {r.status === "ok" ? "RAMP INSIGHT" : r.status === "unsupported" ? "NOT SUPPORTED YET" : "ONE QUESTION"}
                    <em>{finished ? "POST-RACE" : `LAP ${r.current_lap}`}</em>
                  </small>
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

          <div className="pw-controls">
            <div className="pw-chips">
              {suggestions.map((question) => (
                <button type="button" key={question} disabled={busy} onClick={() => askQuestion(question)}>{question}</button>
              ))}
            </div>

            <div className={`pw-question-bank ${showQuestionBank ? "is-open" : ""}`}>
              <button
                type="button"
                className="pw-question-toggle"
                aria-expanded={showQuestionBank}
                onClick={() => setShowQuestionBank((value) => !value)}
              >
                <span>Explore questions ({groups.reduce((total, group) => total + group.questions.length, 0)})</span>
                <ChevronDown size={15} className={showQuestionBank ? "pw-chevron open" : "pw-chevron"} />
              </button>
              {showQuestionBank && (
                <div className="pw-question-groups">
                  {groups.map((group) => {
                    const isOpen = openGroup === group.title;
                    return (
                      <section className="pw-question-group" key={group.title}>
                        <button
                          type="button"
                          className={`pw-group-heading ${isOpen ? "active" : ""}`}
                          aria-expanded={isOpen}
                          onClick={() => setOpenGroup((current) => current === group.title ? "" : group.title)}
                        >
                          <span>{group.title}</span>
                          <span className="pw-group-count">{group.questions.length}</span>
                        </button>
                        {isOpen && (
                          <div className="pw-group-questions">
                            {group.questions.map((question) => (
                              <button type="button" key={question} disabled={busy} onClick={() => askQuestion(question)}>
                                {question}
                              </button>
                            ))}
                          </div>
                        )}
                      </section>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </>
      )}

      <form className="pw-input" onSubmit={submit}>
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={replay.active ? "Ask about this race…" : "Start a replay first"}
          disabled={!replay.active}
          maxLength={500}
          aria-label="Question for the Pit Wall"
        />
        <button type="submit" disabled={!replay.active || busy || !text.trim()} aria-label="Send question"><ArrowUp size={16} /></button>
      </form>
      <p className="pw-foot">Answers are generated from SQL over the available race data. No AI model, no guessing.</p>
    </aside>
  );
}