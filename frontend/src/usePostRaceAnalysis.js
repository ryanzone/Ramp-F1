import { useEffect, useState } from "react";
import { replayApi } from "./api.js";

export function usePostRaceAnalysis(replayId, finished) {
  const [result, setResult] = useState({ replayId: null, data: null, error: null });

  useEffect(() => {
    if (!replayId || !finished) return undefined;
    let cancelled = false;
    replayApi.postRaceAnalysis(replayId)
      .then((data) => {
        if (!cancelled) setResult({ replayId, data, error: null });
      })
      .catch((error) => {
        if (!cancelled) setResult({ replayId, data: null, error: error.message });
      });
    return () => { cancelled = true; };
  }, [replayId, finished]);

  if (!replayId || !finished) return { data: null, loading: false, error: null };
  // No answer for this replay yet: still loading (derived, so no setState inside the effect).
  if (result.replayId !== replayId) return { data: null, loading: true, error: null };
  return { data: result.data, loading: false, error: result.error };
}
