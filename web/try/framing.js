/**
 * Plain-language positioning guidance for participant mode.
 *
 * The geometry mirrors src/ui/framing.py; only the wording differs. The
 * developer overlay says MOVE BACK because a developer wants the shortest
 * unambiguous label. A participant standing three metres away, who has never
 * seen the system before, is told what to do in a sentence.
 *
 * Left and right are avoided: the picture is mirrored, so "step left" is
 * ambiguous to someone watching themselves.
 */

const MARGIN = 0.02;
const MINIMUM_BODY_FILL = 0.45;

const REQUIRED = [
  "left_hip", "right_hip",
  "left_knee", "right_knee",
  "left_shoulder", "right_shoulder",
  "left_ankle", "right_ankle",
];

export function assessFraming(pose) {
  if (!pose || Object.keys(pose.landmarks).length === 0) {
    return { ok: false, message: "STEP INTO VIEW" };
  }

  const names = [...REQUIRED, "nose"].filter((n) => n in pose.landmarks);
  if (names.length === 0) return { ok: false, message: "STEP INTO VIEW" };

  const ys = names.map((n) => pose.landmarks[n].y);
  const xs = names.map((n) => pose.landmarks[n].x);

  const below = ys.some((y) => y > 1 - MARGIN);
  const above = ys.some((y) => y < MARGIN);
  if (below || above) {
    return { ok: false, message: "MOVE FURTHER AWAY" };
  }
  if (xs.some((x) => x < MARGIN) || xs.some((x) => x > 1 - MARGIN)) {
    return { ok: false, message: "MOVE TOWARDS THE MIDDLE" };
  }
  if (Math.max(...ys) - Math.min(...ys) < MINIMUM_BODY_FILL) {
    return { ok: false, message: "MOVE A LITTLE CLOSER" };
  }
  return { ok: true, message: "" };
}
