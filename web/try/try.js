/**
 * Participant mode for the sit-to-stand demonstration.
 *
 * Shows only what helps someone perform the exercise: an instruction, where to
 * stand, and how many repetitions they have done (Document 05 §8, CLAUDE.md
 * §27). Frame rates, landmark confidences and state-machine names belong in
 * the developer sandbox and are deliberately absent here.
 *
 * Pose estimation runs in this tab; the repetition counting runs in a worker,
 * as the project's real Python engine under Pyodide. Nothing is uploaded and
 * nothing is written to disk.
 */

import {
  CANONICAL_CONNECTIONS,
  landmarksToCanonical,
  makePoseFrame,
} from "../canonical.js";
import { assessFraming } from "./framing.js";
import { ArmRaiseDetector, GESTURE_DEFAULTS } from "../gestures.js";
import { PythonScorer } from "../scorer.js";

const TASKS_MODULE =
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18";
const WASM_PATH = `${TASKS_MODULE}/wasm`;
// Served from Google rather than the repository: the model is a large binary
// that is deliberately not committed, and this is the identical file.
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/" +
  "pose_landmarker_lite/float16/1/pose_landmarker_lite.task";

const el = (id) => document.getElementById(id);
const screens = ["intro", "howto", "exercise", "done"];

const state = {
  landmarker: null,
  stream: null,
  running: false,
  startedAt: 0,
  frameIndex: 0,
  lastVideoTime: -1,
  timestamps: [],
  lastPose: null,
  scorer: null,
  awaitingStart: true,
  settleUntilMs: null,
  startGesture: new ArmRaiseDetector({}, 1),
  stopGesture: new ArmRaiseDetector({}, 2),
  banner: "",
  bannerProgress: 0,
  bannerGood: false,
  reps: 0,
  target: null,
  exerciseStartedAt: 0,
};

function show(name) {
  for (const id of screens) el(id).classList.toggle("active", id === name);
  window.scrollTo(0, 0);
}

function setCue(text, kind = "") {
  el("cue").textContent = text;
  el("cue").className = `cue ${kind}`;
}

/* ------------------------------------------------------------------ drawing */

function confidenceColour() {
  // Participants are not shown confidence, so the skeleton is one calm colour
  // rather than a diagnostic traffic light.
  return "rgba(120, 220, 190, 0.85)";
}

function drawSkeleton(context, pose, width, height) {
  const point = (name) => {
    const landmark = pose.landmarks[name];
    return landmark ? [landmark.x * width, landmark.y * height] : null;
  };
  context.strokeStyle = confidenceColour();
  context.fillStyle = confidenceColour();
  context.lineWidth = Math.max(3, width / 400);
  for (const [a, b] of CANONICAL_CONNECTIONS) {
    const start = point(a);
    const end = point(b);
    if (!start || !end) continue;
    context.beginPath();
    context.moveTo(start[0], start[1]);
    context.lineTo(end[0], end[1]);
    context.stroke();
  }
  for (const name of Object.keys(pose.landmarks)) {
    const position = point(name);
    if (!position) continue;
    context.beginPath();
    context.arc(position[0], position[1], Math.max(4, width / 260), 0, Math.PI * 2);
    context.fill();
  }
}

function drawBanner(context, width, height) {
  if (!state.banner) return;
  const scale = Math.max(1, width / 640) * 1.5;
  const size = Math.round(24 * scale);
  context.font = `700 ${size}px ${getComputedStyle(document.body).fontFamily}`;
  context.textAlign = "center";

  const y = height - Math.round(height * 0.08);
  context.fillStyle = "rgba(0, 0, 0, 0.65)";
  context.fillRect(0, y - size - 20, width, size + (state.bannerProgress > 0 ? 62 : 34));

  context.fillStyle = state.bannerGood ? "#6fd48f" : "#ffffff";
  context.fillText(state.banner, width / 2, y);

  if (state.bannerProgress > 0) {
    const barWidth = width * 0.45;
    const left = (width - barWidth) / 2;
    context.fillStyle = "rgba(255,255,255,0.25)";
    context.fillRect(left, y + 14, barWidth, 12);
    context.fillStyle = "#4fbfa8";
    context.fillRect(left, y + 14, barWidth * Math.min(1, state.bannerProgress), 12);
  }
  context.textAlign = "start";
}

/* ------------------------------------------------------------------ gestures */

function updateGestures(pose) {
  if (state.awaitingStart) {
    if (state.settleUntilMs === null) {
      const gesture = state.startGesture.update(pose);
      const framing = assessFraming(pose);
      if (!framing.ok) {
        // Position first: a start signal from someone half out of frame
        // produces a recording that cannot be scored.
        state.banner = framing.message;
        state.bannerProgress = 0;
        state.bannerGood = false;
        return;
      }
      state.banner = gesture.blocked ? "" : "RAISE ONE ARM TO BEGIN";
      state.bannerProgress = gesture.progress;
      state.bannerGood = false;
      if (gesture.triggered) {
        state.settleUntilMs =
          pose.timestamp_ms + GESTURE_DEFAULTS.settleSeconds * 1000;
      }
      return;
    }
    const remaining = (state.settleUntilMs - pose.timestamp_ms) / 1000;
    if (remaining > 0) {
      state.banner = `STARTING IN ${Math.max(0, Math.floor(remaining) + 1)}`;
      state.bannerProgress = 0;
      state.bannerGood = true;
      return;
    }
    state.awaitingStart = false;
    state.settleUntilMs = null;
    state.banner = "";
    beginExercise();
    return;
  }

  const finish = state.stopGesture.update(pose);
  if (finish.raised) {
    state.banner = "RAISE BOTH ARMS TO FINISH";
    state.bannerProgress = finish.progress;
    state.bannerGood = false;
  } else if (state.banner.startsWith("RAISE BOTH")) {
    state.banner = "";
    state.bannerProgress = 0;
  }
  if (finish.triggered) endExercise();
}

/* ------------------------------------------------------------------- session */

async function beginExercise() {
  el("count").hidden = false;
  state.reps = 0;
  state.exerciseStartedAt = performance.now();
  setCue("Stand up, then sit back down.", "");
  try {
    await state.scorer.start(state.target);
  } catch (error) {
    setCue("Could not start counting. You can still try the movement.", "warn");
  }
}

async function endExercise() {
  state.banner = "";
  const result = await state.scorer.stop();
  stopCamera();

  const seconds = Math.round((performance.now() - state.exerciseStartedAt) / 1000);
  el("done-count").textContent = String(result ? result.valid_repetitions : state.reps);
  el("done-time").textContent = `${seconds}s`;
  const mean = result && result.metrics && result.metrics.mean_rep_duration_seconds;
  el("done-mean").textContent = mean ? `${mean.toFixed(1)}s` : "—";
  show("done");
}

/* -------------------------------------------------------------------- camera */

async function startCamera() {
  state.stream = await navigator.mediaDevices.getUserMedia({
    video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
    audio: false,
  });
  el("video").srcObject = state.stream;
  await el("video").play();
}

function stopCamera() {
  state.running = false;
  if (state.stream) {
    for (const track of state.stream.getTracks()) track.stop();
    state.stream = null;
  }
  el("video").pause();
  el("video").srcObject = null;
}

function loop() {
  if (!state.running) return;
  const video = el("video");
  const canvas = el("canvas");
  const width = video.videoWidth;
  const height = video.videoHeight;
  if (!width || !height) {
    requestAnimationFrame(loop);
    return;
  }
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const context = canvas.getContext("2d");

  // Mirrored before inference, so the participant sees themselves the right
  // way round and the landmark sides match the desktop application.
  context.save();
  context.translate(width, 0);
  context.scale(-1, 1);
  context.drawImage(video, 0, 0, width, height);
  context.restore();

  if (video.currentTime !== state.lastVideoTime) {
    state.lastVideoTime = video.currentTime;
    const timestampMs = performance.now() - state.startedAt;
    const result = state.landmarker.detectForVideo(canvas, timestampMs);
    const detected = result.landmarks && result.landmarks.length > 0;
    const pose = makePoseFrame({
      timestampMs,
      landmarks: detected ? landmarksToCanonical(result.landmarks[0]) : {},
      source: "mediapipe_tasks_vision:browser",
      frameIndex: state.frameIndex++,
      imageWidth: width,
      imageHeight: height,
    });
    state.lastPose = pose;
    updateGestures(pose);
    if (state.scorer && state.scorer.active) {
      state.scorer.push(pose, performance.now());
    }
  }

  if (state.lastPose && state.lastPose.person_confidence > 0) {
    drawSkeleton(context, state.lastPose, width, height);
  }
  drawBanner(context, width, height);
  requestAnimationFrame(loop);
}

/* ---------------------------------------------------------------- start-up */

async function startExerciseScreen() {
  show("exercise");
  el("boot").hidden = false;
  el("count").hidden = true;
  setCue("");

  state.scorer = new PythonScorer({
    onProgress: (detail) => {
      el("boot-detail").textContent = detail;
    },
    onReady: () => {
      el("boot-stage").textContent = "Ready";
    },
    onStatus: (status) => {
      state.reps = status.repetitions ?? 0;
      state.target = status.target;
      el("count").firstChild.nodeValue = String(state.reps);
      el("target").textContent = status.target ? ` / ${status.target}` : "";
    },
    onEvent: (event) => {
      if (event.event === "rep_completed") setCue("Good — keep going.", "good");
      if (event.event === "partial_rep") setCue("Try to stand all the way up.", "warn");
    },
    onError: () => {
      setCue("Counting is unavailable, but you can still try the movement.", "warn");
    },
  });

  try {
    await state.scorer.load("../");
    el("boot-stage").textContent = "Asking for the camera";
    await startCamera();

    const vision = await import(TASKS_MODULE);
    const fileset = await vision.FilesetResolver.forVisionTasks(WASM_PATH);
    state.landmarker = await vision.PoseLandmarker.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: MODEL_URL, delegate: "GPU" },
      runningMode: "VIDEO",
      numPoses: 1,
      minPoseDetectionConfidence: 0.5,
      minPosePresenceConfidence: 0.5,
      minTrackingConfidence: 0.5,
      outputSegmentationMasks: false,
    });

    el("boot").hidden = true;
    state.running = true;
    state.startedAt = performance.now();
    state.frameIndex = 0;
    state.awaitingStart = true;
    state.startGesture.reset();
    state.stopGesture.reset();
    requestAnimationFrame(loop);
  } catch (error) {
    // Plain language, and what to do about it.
    el("boot-stage").textContent = "Could not start";
    el("boot-detail").textContent =
      error && String(error).includes("Permission")
        ? "The camera was blocked. Allow camera access for this page and reload."
        : "Something went wrong starting up. Reloading the page usually fixes it.";
  }
}

el("to-howto").addEventListener("click", () => show("howto"));
el("back-intro").addEventListener("click", () => show("intro"));
el("to-exercise").addEventListener("click", startExerciseScreen);
el("finish").addEventListener("click", endExercise);
el("again").addEventListener("click", () => {
  state.awaitingStart = true;
  state.settleUntilMs = null;
  state.reps = 0;
  startExerciseScreen();
});
window.addEventListener("pagehide", stopCamera);
