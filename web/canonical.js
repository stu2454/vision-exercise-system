/**
 * Canonical pose representation for the browser.
 *
 * A deliberate mirror of src/pose/models.py and
 * src/pose/adapters/mediapipe_adapter.py. The landmark names, the MediaPipe
 * index map, the synthetic midpoints and the confidence rules must match the
 * Python implementation exactly, because a pose stream recorded here is meant
 * to be scored by the same tooling as one recorded there.
 *
 * If these two ever disagree, a browser recording and a Python recording of
 * the same movement would produce different results for reasons that have
 * nothing to do with the movement. That is the failure this file exists to
 * prevent, so keep it in step (ADR-007).
 */

export const NOSE = "nose";
export const LEFT_SHOULDER = "left_shoulder";
export const RIGHT_SHOULDER = "right_shoulder";
export const LEFT_ELBOW = "left_elbow";
export const RIGHT_ELBOW = "right_elbow";
export const LEFT_WRIST = "left_wrist";
export const RIGHT_WRIST = "right_wrist";
export const LEFT_HIP = "left_hip";
export const RIGHT_HIP = "right_hip";
export const LEFT_KNEE = "left_knee";
export const RIGHT_KNEE = "right_knee";
export const LEFT_ANKLE = "left_ankle";
export const RIGHT_ANKLE = "right_ankle";
export const LEFT_HEEL = "left_heel";
export const RIGHT_HEEL = "right_heel";
export const LEFT_FOOT = "left_foot";
export const RIGHT_FOOT = "right_foot";
export const SHOULDER_CENTRE = "shoulder_centre";
export const HIP_CENTRE = "hip_centre";

/** Landmarks a pose engine is expected to supply. */
export const MEASURED_LANDMARKS = [
  NOSE,
  LEFT_SHOULDER, RIGHT_SHOULDER,
  LEFT_ELBOW, RIGHT_ELBOW,
  LEFT_WRIST, RIGHT_WRIST,
  LEFT_HIP, RIGHT_HIP,
  LEFT_KNEE, RIGHT_KNEE,
  LEFT_ANKLE, RIGHT_ANKLE,
  LEFT_HEEL, RIGHT_HEEL,
  LEFT_FOOT, RIGHT_FOOT,
];

/**
 * MediaPipe BlazePose 33-point index to canonical name.
 *
 * Identical to MEDIAPIPE_LANDMARK_MAP in the Python adapter. Indices 31/32 are
 * MediaPipe's toe points, the closest available match for foot. Face and hand
 * detail points have no canonical equivalent and are discarded.
 *
 * Tasks for Web uses the same model family as the Python Tasks API, so the
 * indices carry over unchanged — which is the whole reason a browser port is
 * cheap.
 */
export const MEDIAPIPE_LANDMARK_MAP = {
  0: NOSE,
  11: LEFT_SHOULDER, 12: RIGHT_SHOULDER,
  13: LEFT_ELBOW, 14: RIGHT_ELBOW,
  15: LEFT_WRIST, 16: RIGHT_WRIST,
  23: LEFT_HIP, 24: RIGHT_HIP,
  25: LEFT_KNEE, 26: RIGHT_KNEE,
  27: LEFT_ANKLE, 28: RIGHT_ANKLE,
  29: LEFT_HEEL, 30: RIGHT_HEEL,
  31: LEFT_FOOT, 32: RIGHT_FOOT,
};

/** Which measured landmarks each synthetic landmark is the midpoint of. */
const SYNTHETIC_SOURCES = {
  [SHOULDER_CENTRE]: [LEFT_SHOULDER, RIGHT_SHOULDER],
  [HIP_CENTRE]: [LEFT_HIP, RIGHT_HIP],
};

/** Skeleton edges for the overlay, in canonical names only. */
export const CANONICAL_CONNECTIONS = [
  [LEFT_SHOULDER, RIGHT_SHOULDER],
  [LEFT_SHOULDER, LEFT_ELBOW], [LEFT_ELBOW, LEFT_WRIST],
  [RIGHT_SHOULDER, RIGHT_ELBOW], [RIGHT_ELBOW, RIGHT_WRIST],
  [LEFT_SHOULDER, LEFT_HIP], [RIGHT_SHOULDER, RIGHT_HIP],
  [LEFT_HIP, RIGHT_HIP],
  [LEFT_HIP, LEFT_KNEE], [LEFT_KNEE, LEFT_ANKLE],
  [LEFT_ANKLE, LEFT_HEEL], [LEFT_HEEL, LEFT_FOOT], [LEFT_ANKLE, LEFT_FOOT],
  [RIGHT_HIP, RIGHT_KNEE], [RIGHT_KNEE, RIGHT_ANKLE],
  [RIGHT_ANKLE, RIGHT_HEEL], [RIGHT_HEEL, RIGHT_FOOT], [RIGHT_ANKLE, RIGHT_FOOT],
  [SHOULDER_CENTRE, HIP_CENTRE],
];

/**
 * Add synthetic landmarks derivable from the measured ones.
 *
 * A synthetic landmark is the midpoint of its two sources and takes the
 * *lower* of their confidences, so a midpoint is never more trusted than its
 * weakest input. Sources with a null z produce a null z.
 */
export function withSyntheticLandmarks(landmarks) {
  const result = { ...landmarks };
  for (const [name, [firstName, secondName]] of Object.entries(SYNTHETIC_SOURCES)) {
    const first = landmarks[firstName];
    const second = landmarks[secondName];
    if (!first || !second) continue;
    const z = first.z === null || second.z === null ? null : (first.z + second.z) / 2;
    result[name] = {
      x: (first.x + second.x) / 2,
      y: (first.y + second.y) / 2,
      z,
      confidence: Math.min(first.confidence, second.confidence),
    };
  }
  return result;
}

/**
 * Convert one MediaPipe landmark list into canonical landmarks.
 *
 * Confidence comes from `visibility`, matching the Python adapter: occlusion
 * is the failure mode that matters most for exercise scoring.
 */
export function landmarksToCanonical(mediapipeLandmarks) {
  const canonical = {};
  for (const [index, name] of Object.entries(MEDIAPIPE_LANDMARK_MAP)) {
    const raw = mediapipeLandmarks[Number(index)];
    if (!raw) continue;
    canonical[name] = {
      x: raw.x,
      y: raw.y,
      z: raw.z ?? null,
      confidence: raw.visibility ?? 0,
    };
  }
  return withSyntheticLandmarks(canonical);
}

/**
 * Mean confidence across measured landmarks.
 *
 * MediaPipe supplies no per-person detection score, so this is a derived
 * proxy, not a model output. Synthetic landmarks are excluded, or the
 * shoulders and hips would be counted twice.
 */
export function derivePersonConfidence(landmarks) {
  const values = MEASURED_LANDMARKS
    .filter((name) => name in landmarks)
    .map((name) => landmarks[name].confidence);
  if (values.length === 0) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

/**
 * Build a canonical pose frame.
 *
 * A frame with no person detected carries an empty landmark map and a
 * person_confidence of 0, rather than being null, so the recorded stream stays
 * aligned with the captured stream.
 */
export function makePoseFrame({
  timestampMs, landmarks, source, frameIndex, imageWidth, imageHeight,
}) {
  return {
    timestamp_ms: timestampMs,
    person_confidence: derivePersonConfidence(landmarks),
    landmarks,
    source,
    frame_index: frameIndex,
    image_width: imageWidth,
    image_height: imageHeight,
  };
}
