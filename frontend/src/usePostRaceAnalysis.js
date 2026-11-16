import { useEffect, useState } from "react";
import { replayApi } from "./api.js";

export function usePostRaceAnalysis(replayId, finished) {
  const [state, setState] = useState({ replayId: null, data: null, loading: false, error: null });

  useEffect(() => {
    if (!replayId || !finished) return undefined;
    let cancelled = false;
    setState({ replayId, data: null, loading: true, error: null });
    replayApi.postRaceAnalysis(replayId)
      .then((data) => {
        if (!cancelled) setState({ replayId, data, loading: false, error: null });
      })
      .catch((error) => {
        if (!cancelled) setState({ replayId, data: null, loading: false, error: error.message });
      });
    return () => { cancelled = true; };
  }, [replayId, finished]);

  if (state.replayId !== replayId) return { data: null, loading: false, error: null };
  return state;
}
