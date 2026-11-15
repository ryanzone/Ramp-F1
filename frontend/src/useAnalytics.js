import { useCallback, useEffect, useRef, useState } from "react";
import { analyticsApi } from "./api.js";

// The six charts of the Visual Analytics section: each is a real SQL question, asked silently
// (remember = false) so it never changes the chat history or who "him" refers to.
export function chartQuestions(topCodes) {
  const list = [
    { key: "pace", question: "Who has the best race pace?" },
    { key: "positions", question: "Show the position progression" },
    { key: "stints", question: "Show the tyre stints" },
    { key: "pits", question: "How many pit stops has each driver completed?" },
    { key: "tyres", question: "Which tyres are the drivers on right now?" },
  ];
  if (topCodes && topCodes.length >= 2) {
    list.push({ key: "compare", question: `Compare ${topCodes[0]} and ${topCodes[1]} race pace` });
  }
  return list;
}

export function useAnalytics(replayId, server, topCodes) {
  // Everything is keyed by replayId so a new replay starts with a clean conversation.
  const [chat, setChat] = useState({ id: null, messages: [], selectedId: null });
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(null);
  const [liveCharts, setLiveCharts] = useState({ id: null, items: {}, loading: false });
  const socketRef = useRef(null);
  const pendingRef = useRef(null);
  const chartToken = useRef(0);

  const messages = chat.id === replayId ? chat.messages : [];
  const selectedId = chat.id === replayId ? chat.selectedId : null;
  const charts = liveCharts.id === replayId ? liveCharts : { items: {}, loading: false };

  useEffect(
    () => () => {
      if (socketRef.current) socketRef.current.close();
      socketRef.current = null;
    },
    [replayId],
  );

  const ensureSocket = useCallback(
    () =>
      new Promise((resolve) => {
        const current = socketRef.current;
        if (current && current.readyState === WebSocket.OPEN) return resolve(current);
        let settled = false;
        const socket = new WebSocket(analyticsApi.wsUrl());
        const done = (value) => {
          if (!settled) {
            settled = true;
            resolve(value);
          }
        };
        socket.onopen = () => {
          socketRef.current = socket;
          done(socket);
        };
        socket.onerror = () => done(null);
        socket.onclose = () => {
          if (socketRef.current === socket) socketRef.current = null;
          if (pendingRef.current) pendingRef.current.reject(new Error("Analytics connection closed"));
          pendingRef.current = null;
          done(null);
        };
        socket.onmessage = (event) => {
          const m = JSON.parse(event.data);
          if (m.type === "status") setStage(m.stage);
          else if (m.type === "result" && pendingRef.current) {
            pendingRef.current.resolve(m.result);
            pendingRef.current = null;
          } else if (m.type === "error" && pendingRef.current) {
            pendingRef.current.reject(new Error(m.message));
            pendingRef.current = null;
          }
        };
        setTimeout(() => done(null), 2000);
      }),
    [],
  );

  const runQuery = useCallback(
    async (question) => {
      const socket = await ensureSocket();
      if (!socket) return analyticsApi.query(replayId, question); // REST fallback
      return new Promise((resolve, reject) => {
        // A lost answer must never leave the chat stuck on "busy": give up after 30 s.
        const timer = setTimeout(() => {
          pendingRef.current = null;
          reject(new Error("The analyst did not answer in time. Try again."));
        }, 30000);
        pendingRef.current = {
          resolve: (value) => { clearTimeout(timer); resolve(value); },
          reject: (error) => { clearTimeout(timer); reject(error); },
        };
        socket.send(JSON.stringify({ question, replay_id: replayId }));
      });
    },
    [ensureSocket, replayId],
  );

  const push = useCallback(
    (items, selectedId) =>
      setChat((c) => {
        const base = c.id === replayId ? c : { id: replayId, messages: [], selectedId: null };
        return { ...base, messages: base.messages.concat(items), selectedId: selectedId ?? base.selectedId };
      }),
    [replayId],
  );

  const ask = useCallback(
    async (question) => {
      const text = question.trim();
      if (!text || !replayId || busy) return;
      setBusy(true);
      setStage("parsing");
      push([{ role: "user", id: `u${Date.now()}`, text }]);
      try {
        const result = await runQuery(text);
        push([{ role: "analyst", id: result.id, result }], result.sql ? result.id : null);
      } catch (err) {
        push([{ role: "error", id: `e${Date.now()}`, text: err.message }]);
      } finally {
        setBusy(false);
        setStage(null);
      }
    },
    [replayId, busy, push, runQuery],
  );

  const select = useCallback(
    (id) => setChat((c) => (c.id === replayId ? { ...c, selectedId: id } : c)),
    [replayId],
  );

  // Charts refresh once per lap and after every seek, never faster: they show the replay clock.
  const lapKey = server ? `${server.epoch}:${server.current_lap}` : null;
  const topKey = (topCodes || []).slice(0, 2).join(",");
  useEffect(() => {
    if (!replayId || !lapKey) return undefined;
    const token = ++chartToken.current;
    const timer = setTimeout(async () => {
      setLiveCharts((c) => ({ id: replayId, items: c.id === replayId ? c.items : {}, loading: true }));
      const questions = chartQuestions(topKey ? topKey.split(",") : []);
      const settled = await Promise.allSettled(
        questions.map((q) => analyticsApi.query(replayId, q.question, false)),
      );
      if (token !== chartToken.current) return;
      const items = {};
      settled.forEach((r, i) => {
        items[questions[i].key] = r.status === "fulfilled" ? r.value : { status: "error", answer: r.reason.message };
      });
      setLiveCharts({ id: replayId, items, loading: false });
    }, 400);
    return () => clearTimeout(timer);
  }, [replayId, lapKey, topKey]);

  const selected = messages.find((m) => m.id === selectedId && m.result)?.result || null;
  return { messages, busy, stage, selected, selectedId, ask, select, charts: charts.items, chartsLoading: charts.loading };
}
