import type { Camera } from "../api/cameras";

type Props = {
  camera: Camera; busy: boolean; canOperate: boolean;
  onTest: () => void; onStart: () => void; onStop: () => void; onSnapshot: () => void;
  onPtz: (action: "move" | "stop" | "home", pan?: number, tilt?: number) => void;
};

export default function CameraControls({ camera, busy, canOperate, onTest, onStart, onStop, onSnapshot, onPtz }: Props) {
  const caps = camera.capabilities;
  const off = busy || !canOperate;
  const ptz = !!caps?.ptz;
  const pad: [string, number, number][] = [["↖", -1, 1], ["↑", 0, 1], ["↗", 1, 1], ["←", -1, 0], ["■", 0, 0], ["→", 1, 0], ["↙", -1, -1], ["↓", 0, -1], ["↘", 1, -1]];
  return (
    <div className="camera-controls">
      {!canOperate && <p className="muted">Enter the operator key to test, stream or control cameras.</p>}
      <div className="row">
        <button disabled={off} onClick={onTest}>TEST CONNECTION</button>
        <button disabled={off || !caps?.preview || camera.stream_active} onClick={onStart} title={caps?.preview ? "" : "Needs a media gateway and playback path"}>START STREAM</button>
        <button disabled={off || !camera.stream_active} onClick={onStop}>STOP STREAM</button>
      </div>
      <div className="row">
        <button disabled={off || !caps?.snapshot} onClick={onSnapshot} title={caps?.snapshot ? "" : "Snapshot is not supported for this camera"}>SNAPSHOT</button>
      </div>
      <div className={"ptz-pad" + (ptz ? "" : " unsupported")} role="group" aria-label="PTZ controls">
        {pad.map(([label, p, t]) => (
          <button key={label} disabled={off || !ptz} aria-label={`PTZ ${label}`}
            onClick={() => (p === 0 && t === 0 ? onPtz("stop") : onPtz("move", p, t))}>{label}</button>
        ))}
      </div>
      {!ptz && <p className="muted">PTZ is not available for this camera.</p>}
    </div>
  );
}
