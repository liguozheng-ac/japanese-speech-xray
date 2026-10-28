import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "../motion/useReducedMotion";
import { HeroBackground } from "./StaticBlueWave";

const poster = "/local-backgrounds/58-poster.jpg";

/** Local decorative media only; the original wave remains the failure fallback. */
export function HeroVideoBackground() {
  const reducedMotion = useReducedMotion();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const [source] = useState(() =>
    window.matchMedia("(max-width: 760px)").matches
      ? "/local-backgrounds/58-mobile.mp4"
      : "/local-backgrounds/58-desktop.mp4",
  );

  useEffect(() => {
    const video = videoRef.current;
    if (!video || failed || reducedMotion) return;
    let inView = true;
    let disposed = false;
    const syncPlayback = () => {
      if (document.hidden || !inView) {
        video.pause();
      } else {
        void video.play().catch((error: unknown) => {
          // A pause/unmount may interrupt an in-flight play request.
          if (!disposed && error instanceof DOMException && error.name === "NotAllowedError") {
            setFailed(true);
          }
        });
      }
    };
    const observer = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      syncPlayback();
    });
    observer.observe(video);
    document.addEventListener("visibilitychange", syncPlayback);
    syncPlayback();
    return () => {
      disposed = true;
      observer.disconnect();
      document.removeEventListener("visibilitychange", syncPlayback);
      video.pause();
    };
  }, [failed, reducedMotion]);

  if (failed) return <HeroBackground />;

  return (
    <div className="hero-background hero-video-background" aria-hidden="true">
      {reducedMotion ? (
        <img className="hero-video-media" src={poster} alt="" onError={() => setFailed(true)} />
      ) : (
        <video
          ref={videoRef}
          className="hero-video-media"
          src={source}
          poster={poster}
          autoPlay
          muted
          loop
          playsInline
          preload="metadata"
          onError={() => setFailed(true)}
        />
      )}
    </div>
  );
}
