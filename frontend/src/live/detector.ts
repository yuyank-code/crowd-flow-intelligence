/**
 * In-browser people counting. The model (CenterNet, COCO classes) is bundled in /models, so nothing is
 * downloaded from third parties and video frames never leave this tab: only the resulting number is sent.
 * It counts people-shaped objects. It does not identify anyone and keeps no images.
 */
import type { Human } from "@vladmandic/human";

export type Box = { x: number; y: number; w: number; h: number; score: number };
export type Detection = { people: number; boxes: Box[]; videoWidth: number; videoHeight: number };

let loading: Promise<Human> | null = null;

export const MIN_CONFIDENCE = 0.45;

export function loadDetector(): Promise<Human> {
  if (!loading) {
    loading = (async () => {
      const { Human } = await import("@vladmandic/human");
      const human = new Human({
        modelBasePath: "/models/",
        backend: "webgl",
        cacheSensitivity: 0,          // run the model on every frame we ask about
        warmup: "none",
        filter: { enabled: false },
        face: { enabled: false }, body: { enabled: false }, hand: { enabled: false },
        gesture: { enabled: false }, segmentation: { enabled: false },
        object: { enabled: true, modelPath: "centernet.json", minConfidence: MIN_CONFIDENCE, iouThreshold: 0.4, maxDetected: 200, skipFrames: 0, skipTime: 0 },
      });
      await human.load();
      return human;
    })().catch(e => { loading = null; throw e; });
  }
  return loading;
}

/** Count people in the current video frame. */
export async function countPeople(video: HTMLVideoElement): Promise<Detection> {
  const human = await loadDetector();
  const result = await human.detect(video);
  const boxes = result.object
    .filter(o => o.label === "person" && o.score >= MIN_CONFIDENCE)
    .map(o => ({ x: o.box[0], y: o.box[1], w: o.box[2], h: o.box[3], score: o.score }));
  return { people: boxes.length, boxes, videoWidth: video.videoWidth, videoHeight: video.videoHeight };
}

/** Median of the last few counts: one noisy frame should not flip the risk level. */
export function smoother(size = 3) {
  const last: number[] = [];
  return (n: number) => {
    last.push(n);
    if (last.length > size) last.shift();
    const sorted = [...last].sort((a, b) => a - b);
    return sorted[Math.floor(sorted.length / 2)];
  };
}
