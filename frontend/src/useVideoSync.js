import { useCallback, useEffect, useRef, useState } from "react";

// Local, user-supplied recordings only: a file picked from disk or a direct media URL the user
// is entitled to watch. Nothing is downloaded, scraped or proxied by RAMP.
export function useVideoSync(replay, syncOffset) {
  const elementRef = useRef(null);
  const [src, setSrcState] = useState("");
  const [follow, setFollow] = useState(false);
  const objectUrl = useRef(null);

  // Callback ref for the <video> element; everything that touches it goes through the functions below.
  const attach = useCallback((node) => {
    elementRef.current = node;
  }, []);
  const getTime = useCallback(() => (elementRef.current ? elementRef.current.currentTime : 0), []);
  const setTime = useCallback((seconds) => {
    if (elementRef.current) elementRef.current.currentTime = Math.max(0, seconds);
  }, []);

  const setSrc = useCallback((next, isObjectUrl = false) => {
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = isObjectUrl ? next : null;
    setSrcState(next);
  }, []);

  useEffect(
    () => () => {
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    },
    [],
  );

  const { server } = replay;
  const replayElapsed = server ? server.elapsed : 0;
  const playing = server?.state === "playing";

  // "Follow replay" is opt-in; by default the video and the replay have independent controls.
  useEffect(() => {
    const video = elementRef.current;
    if (!follow || !video || !server) return;
    const target = Math.max(0, replayElapsed - syncOffset);
    if (Math.abs(video.currentTime - target) > 1.5) video.currentTime = target;
    if (playing && video.paused) video.play().catch(() => {});
    if (!playing && !video.paused) video.pause();
  }, [follow, server, replayElapsed, playing, syncOffset]);

  return { attach, getTime, setTime, src, setSrc, follow, setFollow };
}
