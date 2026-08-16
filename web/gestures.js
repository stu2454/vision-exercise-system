/**
 * Gesture detection, mirroring src/movement/gestures.py.
 *
 * The participant starts and stops recording without touching the keyboard.
 * Without this, a browser recording carries exactly the contamination the
 * gesture was built to remove in Python: walking to the machine to press a
 * button puts that walk into the recording, and hip height moves further while
 * crossing a room than it does during a repetition.
 *
 * The thresholds must match the Python ones, or the two runtimes would accept
 * different arm positions and a recording made in one would not be comparable
 * with a recording made in the other. tests/unit/test_web_parity.py checks
 * they agree.
 */

import { angleAt, aspectRatio, pointOf } from "./geometry.js";

const ARM_SIDES = [
  ["left", "left_shoulder", "left_elbow", "left_wrist"],
  ["right", "right_shoulder", "right_elbow", "right_wrist"],
];

/** Matches ArmRaiseConfig and GestureConfig in Python. */
export const GESTURE_DEFAULTS = {
  minimumElbowAngle: 50.0,
  maximumElbowAngle: 130.0,
  requireWristAboveShoulder: true,
  minimumConfidence: 0.6,
  startHoldMs: 800.0,
  stopHoldMs: 600.0,
  settleSeconds: 3.0,
};

/**
 * Canonical sides of every raised, bent arm.
 *
 * A straight arm overhead is rejected deliberately: it is close to the arm
 * positions that occur naturally while standing up from a chair.
 */
export function raisedArmSides(pose, config) {
  if (!pose || Object.keys(pose.landmarks).length === 0) return [];
  const sides = [];
  const aspect = aspectRatio(pose);

  for (const [side, shoulderName, elbowName, wristName] of ARM_SIDES) {
    const parts = [shoulderName, elbowName, wristName].map(
      (name) => pose.landmarks[name],
    );
    if (parts.some((p) => !p)) continue;
    if (Math.min(...parts.map((p) => p.confidence)) < config.minimumConfidence) {
      continue;
    }

    const shoulder = pointOf(pose, shoulderName, aspect);
    const elbow = pointOf(pose, elbowName, aspect);
    const wrist = pointOf(pose, wristName, aspect);
    if (!shoulder || !elbow || !wrist) continue;

    // y increases downwards, so "above" is a smaller y.
    if (config.requireWristAboveShoulder && wrist[1] >= shoulder[1]) continue;

    const angle = angleAt(shoulder, elbow, wrist);
    if (angle === null) continue;
    if (angle >= config.minimumElbowAngle && angle <= config.maximumElbowAngle) {
      sides.push(side);
    }
  }
  return sides;
}

/**
 * Detects raised, bent arms held long enough to be deliberate.
 *
 * Timing comes from frame timestamps rather than a frame count, so the hold is
 * the same whether the browser is running at 30 or 60 fps — which it does,
 * depending on what the camera negotiates.
 *
 * `requiredArms` is 1 to start and 2 to stop. The stop hold is *shorter*: both
 * arms raised together is far stronger evidence of intent than one, and a long
 * hold failed twice in practice, sending the participant to the keyboard.
 */
export class ArmRaiseDetector {
  constructor(config = {}, requiredArms = 1) {
    if (requiredArms !== 1 && requiredArms !== 2) {
      throw new Error("requiredArms must be 1 or 2");
    }
    this.config = { ...GESTURE_DEFAULTS, ...config };
    this.requiredArms = requiredArms;
    this.holdMs =
      config.holdMs ??
      (requiredArms === 2 ? this.config.stopHoldMs : this.config.startHoldMs);
    this.reset();
  }

  reset() {
    this.sinceMs = null;
    this.fired = false;
  }

  update(pose) {
    const now = pose.timestamp_ms;
    const sides = raisedArmSides(pose, this.config);

    if (sides.length < this.requiredArms) {
      this.sinceMs = null;
      return { raised: false, side: null, heldMs: 0, progress: 0, triggered: false };
    }

    if (this.sinceMs === null) this.sinceMs = now;
    const heldMs = now - this.sinceMs;
    const progress = this.holdMs <= 0 ? 1 : Math.min(1, heldMs / this.holdMs);

    let triggered = false;
    if (heldMs >= this.holdMs && !this.fired) {
      triggered = true;
      this.fired = true;
    }

    return {
      raised: true,
      side: sides.length > 1 ? "both" : sides[0],
      heldMs,
      progress,
      triggered,
    };
  }
}
