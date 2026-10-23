import { useEffect, useRef, useState } from "react";
import { cameras } from "../api/cameras";

type Props = { cameraId: string; active: boolean; supported: boolean; onVideo?: (el: HTMLVideoElement | null) => void };

/** Plays the gateway's short-lived HLS reference. Never receives a raw RTSP URL or credentials. */
export default function CameraPreview({ cameraId, active, supported, onVideo }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState<"idle" | "loading" | "playing" | "error">("idle");
  const [message, setMessage] = useState("");

  // Let a parent (e.g. the live people counter) read frames from the playing <video>.
  useEffect(() => { onVideo?.(active && supported ? video.current : null); return () => onVideo?.(null); }, [active, supported, onVideo]);

  useEffect(() => {
    if (!active || !supported) { setState("idle"); return; }
    let hls: { destroy(): void } | undefined, cancelled = false, refresh: number | undefined;
    let token = "";
    setState("loading"); setMessage("");
    (async () => {
      try {
        const ref = await cameras.playback(cameraId);
        const el = video.current;
        if (cancelled || !el) return;
        const tokenOf = (u: string) => new URL(u).searchParams.get("token") ?? "";
        token = tokenOf(ref.url);
        // Tokens are short-lived; renew well before expiry so playlist and segment requests keep passing the gateway check.
        const ttlMs = Math.max(5000, new Date(ref.expires_at).getTime() - Date.now());
        const renew = async (native: boolean) => {
          try {
            const next = await cameras.playback(cameraId);
            token = tokenOf(next.url);
            if (native && video.current) { const t = video.current.currentTime; video.current.src = next.url; video.current.currentTime = t; void video.current.play().catch(() => undefined); }
          } catch { if (!cancelled) { setState("error"); setMessage("Playback token could not be renewed."); } }
        };
        if (el.canPlayType("application/vnd.apple.mpegurl")) {          // Safari / iOS: native HLS (cannot add headers; source is re-set on renewal)
          el.src = ref.url;
          refresh = window.setInterval(() => void renew(true), ttlMs * 0.6);
        } else {
          const { default: Hls } = await import("hls.js");
          if (!Hls.isSupported()) throw new Error("This browser cannot play HLS video.");
          // hls.js does not carry the playlist's query string to segment requests, so add the current token to every request.
          const h = new Hls({
            lowLatencyMode: true,
            xhrSetup: (xhr: XMLHttpRequest, url: string) => {
              const u = new URL(url); u.searchParams.set("token", token); xhr.open("GET", u.toString(), true);
            },
          });
          refresh = window.setInterval(() => void renew(false), ttlMs * 0.6);
          h.on(Hls.Events.ERROR, (_e, d) => { if (d.fatal) { setState("error"); setMessage(`Stream error: ${d.details}`); } });
          h.loadSource(ref.url); h.attachMedia(el); hls = h;
        }
        await el.play().catch(() => undefined);       // autoplay may be blocked; controls remain available
        if (!cancelled) setState("playing");
      } catch (e) {
        if (!cancelled) { setState("error"); setMessage((e as Error).message); }
      }
    })();
    return () => { cancelled = true; window.clearInterval(refresh); hls?.destroy(); if (video.current) { video.current.removeAttribute("src"); video.current.load(); } };
  }, [cameraId, active, supported]);

  if (!supported) return <div className="preview empty">Live preview unavailable: needs a media gateway and a playback path for this camera.</div>;
  if (!active) return <div className="preview empty">Stream is stopped. Press “Start stream” to request a live preview.</div>;
  return (
    <div className="preview">
      <video ref={video} controls muted playsInline aria-label="Live camera preview" />
      {state === "loading" && <p className="muted">Connecting to stream…</p>}
      {state === "error" && <p className="error-text" role="alert">{message || "Preview failed."}</p>}
      <small className="muted">Live camera video. No analytics are applied; nothing here is a crowd count.</small>
    </div>
  );
}
