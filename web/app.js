/**
 * Browser Pose Sandbox — a spike, not a port.
 *
 * Answers one question: does pose estimation run acceptably in a browser, on
 * this machine and on a tablet? Document 03 §7 and ADR-010 are explicit that
 * the Python and browser implementations must not be built simultaneously, so
 * this deliberately stops at pose. No filtering, no features, no state
 * machine, no exercise logic.
 *
 * What it does do is record in the canonical pose-stream format, so a
 * recording made here can be scored by the existing Python tooling and
 * compared against a Python recording of the same movement.
 */

import {
  CANONICAL_CONNECTIONS,
  landmarksToCanonical,
  makePoseFrame,
} from "./canonical.js";
import { ScoringBridge } from "./bridge.js";
import { ArmRaiseDetector, GESTURE_DEFAULTS } from "./gestures.js";
import { PoseStreamRecorder } from "./recorder.js";

const MODEL_PATH = "../models/pose_landmarker_lite.task";
const WASM_PATH =
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18/wasm";
const TASKS_MODULE =
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18";

const REQUESTED_WIDTH = 1280;
const REQUESTED_HEIGHT = 720;

/** Frames needed before a measured frame rate is trusted, as in Python. */
const MINIMUM_RATE_SAMPLES = 10;

const el = (id) => document.getElementById(id);

const ui = {
  video: el("video"),
  canvas: el("canvas"),
  start: el("start"),
  stop: el("stop"),
  record: el("record"),
  download: el("download"),
  skeleton: el("skeleton"),
  gestures: el("gestures"),
  reps: el("reps"),
  exerciseState: el("exercise-state"),
  view: el("view"),
  status: el("status"),
  fps: el("fps"),
  inference: el("inference"),
  confidence: el("confidence"),
  landmarks: el("landmarks"),
  frames: el("frames"),
  resolution: el("resolution"),
};

const state = {
  landmarker: null,
  stream: null,
  running: false,
  startedAt: 0,
  frameIndex: 0,
  lastVideoTime: -1,
  timestamps: [],
  inferenceTimes: [],
  showSkeleton: true,
  recorder: new PoseStreamRecorder(),
  // Gesture control, matching the Python `exercise` command. Nothing is
  // recorded until the participant signals, so the walk into position never
  // reaches the recording.
  gesturesEnabled: true,
  startGesture: new ArmRaiseDetector({}, 1),
  stopGesture: new ArmRaiseDetector({}, 2),
  awaitingStart: true,
  settleUntilMs: null,
  prompt: "",
  promptProgress: 0,
  // Scoring runs in Python. The browser sends canonical pose frames and
  // displays what comes back; it never interprets movement itself.
  bridge: null,
  reps: null,
  target: null,
  exerciseState: "",
};

/** Rolling frame-rate estimate from delivered frame timestamps. */
function measuredFps() {
  const t = state.timestamps;
  if (t.length < MINIMUM_RATE_SAMPLES) return null;
  const elapsed = t[t.length - 1] - t[0];
  if (elapsed <= 0) return null;
  return ((t.length - 1) * 1000) / elapsed;
}

function meanInference() {
  const v = state.inferenceTimes;
  if (v.length === 0) return null;
  return v.reduce((a, b) => a + b, 0) / v.length;
}

function setStatus(text, kind = "") {
  ui.status.textContent = text;
  ui.status.className = kind;
}

function confidenceColour(confidence) {
  if (confidence >= 0.6) return "#78dc8c";
  if (confidence >= 0.3) return "#f0be28";
  return "#eb4646";
}

function drawSkeleton(context, pose, width, height) {
  const point = (name) => {
    const landmark = pose.landmarks[name];
    if (!landmark) return null;
    return [landmark.x * width, landmark.y * height];
  };

  context.lineWidth = Math.max(2, width / 500);
  for (const [startName, endName] of CANONICAL_CONNECTIONS) {
    const start = point(startName);
    const end = point(endName);
    if (!start || !end) continue;
    const confidence = Math.min(
      pose.landmarks[startName].confidence,
      pose.landmarks[endName].confidence,
    );
    context.strokeStyle = confidenceColour(confidence);
    context.beginPath();
    context.moveTo(start[0], start[1]);
    context.lineTo(end[0], end[1]);
    context.stroke();
  }

  const radius = Math.max(3, width / 320);
  for (const [name, landmark] of Object.entries(pose.landmarks)) {
    const position = point(name);
    if (!position) continue;
    context.fillStyle = confidenceColour(landmark.confidence);
    context.beginPath();
    context.arc(position[0], position[1], radius, 0, Math.PI * 2);
    context.fill();
  }
}

/**
 * A large instruction across the image, readable from across a room.
 *
 * The ordinary readout is unreadable at the distance a participant stands to
 * exercise, which is how two Python takes came to be recorded with the legs
 * out of frame.
 */
/**
 * The repetition count, large enough to read from the chair.
 *
 * The one number worth seeing during an exercise, so it is drawn at the size
 * that makes it readable across a room rather than in the readout strip.
 */
function drawRepetitionCount(context, width, height) {
  const text = state.target ? `${state.reps} / ${state.target}` : `${state.reps}`;
  const size = Math.round(Math.max(48, width / 11));
  context.font = `700 ${size}px ui-monospace, Menlo, monospace`;
  context.textAlign = "end";
  const x = width - Math.round(width * 0.03);
  const y = height - Math.round(height * 0.16);
  context.lineWidth = Math.max(4, size / 12);
  context.strokeStyle = "rgba(0, 0, 0, 0.75)";
  context.strokeText(text, x, y);
  context.fillStyle = "#78dc8c";
  context.fillText(text, x, y);
  context.textAlign = "start";
}

function drawBanner(context, text, progress, width, height) {
  const scale = Math.max(1, width / 640) * 1.4;
  const fontSize = Math.round(22 * scale);
  context.font = `700 ${fontSize}px ui-monospace, Menlo, monospace`;
  context.textAlign = "center";

  const y = height - Math.round(height * 0.07);
  const bandTop = y - fontSize - 18;
  const bandBottom = y + (progress > 0 ? 34 : 16);

  context.fillStyle = "rgba(0, 0, 0, 0.62)";
  context.fillRect(0, bandTop, width, bandBottom - bandTop);

  context.fillStyle = "#28c8f0";
  context.fillText(text, width / 2, y);

  if (progress > 0) {
    const barWidth = width * 0.5;
    const left = (width - barWidth) / 2;
    const top = y + 12;
    context.fillStyle = "#464646";
    context.fillRect(left, top, barWidth, 10);
    context.fillStyle = "#28c8f0";
    context.fillRect(left, top, barWidth * Math.min(1, progress), 10);
  }
  context.textAlign = "start";
}

/**
 * Advance the gesture state machine for one frame.
 *
 * Start: one raised arm, then a settle pause so the arm can come down and the
 * participant can be still before anything is measured.
 * Stop: both arms raised.
 */
function updateGestures(pose) {
  if (!state.gesturesEnabled) return;

  if (state.awaitingStart) {
    if (state.settleUntilMs === null) {
      const gesture = state.startGesture.update(pose);
      state.prompt = "RAISE AN ARM TO RECORD";
      state.promptProgress = gesture.progress;
      if (gesture.triggered) {
        state.settleUntilMs =
          pose.timestamp_ms + GESTURE_DEFAULTS.settleSeconds * 1000;
      }
      return;
    }
    const remaining = (state.settleUntilMs - pose.timestamp_ms) / 1000;
    if (remaining > 0) {
      state.prompt = `STARTING IN ${Math.max(0, Math.floor(remaining) + 1)}`;
      state.promptProgress = 0;
      return;
    }
    state.awaitingStart = false;
    state.settleUntilMs = null;
    state.prompt = "";
    state.promptProgress = 0;
    beginRecording();
    return;
  }

  const finish = state.stopGesture.update(pose);
  if (finish.raised) {
    state.prompt = "RAISE BOTH ARMS TO FINISH";
    state.promptProgress = finish.progress;
  } else if (state.prompt.startsWith("RAISE BOTH")) {
    state.prompt = "";
    state.promptProgress = 0;
  }
  if (finish.triggered) {
    endRecording();
    state.prompt = "";
    state.promptProgress = 0;
  }
}

async function createLandmarker() {
  setStatus("Loading pose model…");
  const vision = await import(TASKS_MODULE);
  const fileset = await vision.FilesetResolver.forVisionTasks(WASM_PATH);
  state.landmarker = await vision.PoseLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: MODEL_PATH, delegate: "GPU" },
    runningMode: "VIDEO",
    // One participant, matching the Python engine (Document 03 §37).
    numPoses: 1,
    minPoseDetectionConfidence: 0.5,
    minPosePresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
    outputSegmentationMasks: false,
  });
}

async function startCamera() {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: {
      width: { ideal: REQUESTED_WIDTH },
      height: { ideal: REQUESTED_HEIGHT },
      facingMode: "user",
    },
    audio: false,
  });
  state.stream = stream;
  ui.video.srcObject = stream;
  await ui.video.play();
}

/**
 * Release the camera and clear the picture.
 *
 * Every track must be stopped explicitly. Pausing the video or dropping the
 * element's reference is not enough — the camera stays live, the indicator
 * light stays on, and the last frame stays on screen. Anything that ends a
 * session routes through here, including the page being closed.
 */
function releaseCamera() {
  if (state.stream) {
    for (const track of state.stream.getTracks()) track.stop();
    state.stream = null;
  }
  ui.video.pause();
  ui.video.srcObject = null;
}

function stopEverything(message = "Camera off.") {
  state.running = false;
  releaseCamera();

  if (state.recorder.recording) {
    state.recorder.stop();
    ui.record.textContent = "Start recording";
    ui.record.classList.remove("recording");
    // A recording in progress is kept, not discarded: it is still
    // downloadable, and silently binning someone's take would be worse than
    // ending it early.
    ui.download.disabled = state.recorder.frameCount === 0;
  }

  if (state.landmarker) {
    state.landmarker.close();
    state.landmarker = null;
  }

  const context = ui.canvas.getContext("2d");
  context.clearRect(0, 0, ui.canvas.width, ui.canvas.height);
  context.fillStyle = "#000";
  context.fillRect(0, 0, ui.canvas.width, ui.canvas.height);

  if (state.bridge) {
    state.bridge.stop();
    state.bridge = null;
  }
  state.reps = null;
  state.target = null;
  ui.reps.textContent = "—";
  ui.exerciseState.textContent = "—";
  state.lastPose = null;
  state.prompt = "";
  state.promptProgress = 0;
  state.lastVideoTime = -1;
  state.timestamps = [];
  state.inferenceTimes = [];

  ui.start.disabled = false;
  ui.stop.disabled = true;
  ui.record.disabled = true;
  ui.fps.textContent = "—";
  ui.inference.textContent = "—";
  ui.confidence.textContent = "—";
  ui.landmarks.textContent = "0";
  ui.resolution.textContent = "—";
  setStatus(message);
}

function loop() {
  if (!state.running) return;

  const width = ui.video.videoWidth;
  const height = ui.video.videoHeight;
  if (!width || !height) {
    requestAnimationFrame(loop);
    return;
  }

  if (ui.canvas.width !== width || ui.canvas.height !== height) {
    ui.canvas.width = width;
    ui.canvas.height = height;
  }
  // Set every frame rather than only on a size change. The canvas starts at
  // 1280x720 in the markup, so when the camera delivers exactly that the
  // condition above never fires and the readout stayed blank — which looked
  // like the camera had failed to report a size when it had not.
  ui.resolution.textContent = `${width}x${height}`;

  const context = ui.canvas.getContext("2d");

  // Mirror before inference, matching WebcamFrameSource(mirror=True). Doing it
  // here rather than with a CSS transform means the landmarks describe the
  // mirrored image, so canonical left and right mean the same thing as they do
  // in a Python recording.
  context.save();
  context.translate(width, 0);
  context.scale(-1, 1);
  context.drawImage(ui.video, 0, 0, width, height);
  context.restore();

  // Only run inference on a genuinely new video frame. requestAnimationFrame
  // fires at display rate, which is usually faster than the camera, and
  // re-running on an unchanged frame would inflate the frame-rate figure.
  if (ui.video.currentTime !== state.lastVideoTime) {
    state.lastVideoTime = ui.video.currentTime;
    const timestampMs = performance.now() - state.startedAt;

    const began = performance.now();
    const result = state.landmarker.detectForVideo(ui.canvas, timestampMs);
    const inferenceMs = performance.now() - began;

    const detected = result.landmarks && result.landmarks.length > 0;
    const landmarks = detected ? landmarksToCanonical(result.landmarks[0]) : {};
    const pose = makePoseFrame({
      timestampMs,
      landmarks,
      source: "mediapipe_tasks_vision:browser",
      frameIndex: state.frameIndex,
      imageWidth: width,
      imageHeight: height,
    });

    state.frameIndex += 1;
    state.timestamps.push(timestampMs);
    if (state.timestamps.length > 120) state.timestamps.shift();
    state.inferenceTimes.push(inferenceMs);
    if (state.inferenceTimes.length > 60) state.inferenceTimes.shift();

    updateGestures(pose);

    if (state.bridge && state.bridge.active) {
      state.bridge.push(pose, performance.now());
    }

    if (state.recorder.recording) {
      state.recorder.write(pose);
      ui.frames.textContent = String(state.recorder.frameCount);
    }

    state.lastPose = pose;

    const fps = measuredFps();
    ui.fps.textContent = fps === null ? "—" : fps.toFixed(1);
    const inference = meanInference();
    ui.inference.textContent = inference === null ? "—" : `${inference.toFixed(1)} ms`;
    ui.confidence.textContent = detected ? pose.person_confidence.toFixed(2) : "—";
    ui.landmarks.textContent = detected ? String(Object.keys(landmarks).length) : "0";
  }

  if (state.showSkeleton && state.lastPose && state.lastPose.person_confidence > 0) {
    drawSkeleton(context, state.lastPose, width, height);
  }

  if (state.reps !== null) {
    drawRepetitionCount(context, width, height);
  }

  if (state.prompt) {
    drawBanner(context, state.prompt, state.promptProgress, width, height);
  }

  requestAnimationFrame(loop);
}

async function onStart() {
  ui.start.disabled = true;
  try {
    await createLandmarker();
    setStatus("Requesting camera…");
    await startCamera();
    state.running = true;
    state.startedAt = performance.now();
    state.frameIndex = 0;
    setStatus("Running", "ok");
    ui.record.disabled = false;
    ui.stop.disabled = false;
    armGestures();
    requestAnimationFrame(loop);
  } catch (error) {
    // Say what went wrong and what to do about it.
    setStatus(`Could not start: ${error.message}`, "bad");
    releaseCamera();
    ui.start.disabled = false;
  }
}

/**
 * Start recording. One path, used by both the gesture and the button, so the
 * two cannot diverge.
 */
function beginRecording() {
  if (state.recorder.recording) return true;

  const fps = measuredFps();
  if (fps === null) {
    // Refusing rather than guessing: a wrong frame rate in the metadata is
    // the defect that cost a 2x timing error in the Python recorder.
    setStatus("Wait a moment — measuring the frame rate first.", "warn");
    return false;
  }

  const track = state.stream ? state.stream.getVideoTracks()[0] : null;
  const trackSettings = track && track.getSettings ? track.getSettings() : null;

  const id = state.recorder.start({
    measuredFps: fps,
    trackSettings,
    width: ui.canvas.width,
    height: ui.canvas.height,
    cameraView: ui.view.value,
    poseEngine: "mediapipe_tasks_vision",
    poseModelVersion: "pose_landmarker_lite.task",
  });
  ui.record.textContent = "Stop recording";
  ui.record.classList.add("recording");
  ui.frames.textContent = "0";
  setStatus(`Recording ${id}`, "rec");
  startScoring();
  return true;
}

/** Open a scoring session with the Python server, if one is reachable. */
function startScoring() {
  state.bridge = new ScoringBridge({
    onStatus: (data) => {
      state.reps = data.repetitions;
      state.target = data.target;
      state.exerciseState = data.state || "";
      ui.reps.textContent =
        data.target ? `${data.repetitions} / ${data.target}` : String(data.repetitions);
      ui.exerciseState.textContent =
        (data.state || "—") + (data.calibrated ? "" : " (calibrating)");
    },
    onEvent: (event) => {
      if (event.event === "rep_completed") {
        setStatus(`Repetition ${event.sequence}`, "ok");
      }
    },
    onError: (message) => setStatus(message, "warn"),
  });
  state.bridge.start().catch(() => {
    // The page is usable without the scorer: it still records, and the file
    // can be scored afterwards. Say so rather than appearing broken.
    state.bridge = null;
    setStatus(
      "Recording without live scoring — run tools/exercise_server.py for a live count.",
      "warn",
    );
  });
}

async function endRecording() {
  if (!state.recorder.recording) return;
  const id = state.recorder.stop();
  ui.record.textContent = "Start recording";
  ui.record.classList.remove("recording");
  ui.download.disabled = state.recorder.frameCount === 0;

  let summary = `Recorded ${state.recorder.frameCount} frames as ${id}`;
  if (state.bridge && state.bridge.active) {
    const result = await state.bridge.stop();
    if (result) {
      const mean = result.metrics && result.metrics.mean_rep_duration_seconds;
      summary +=
        ` — ${result.valid_repetitions} repetitions` +
        (mean ? `, mean ${mean.toFixed(2)}s` : "");
    }
  }
  setStatus(summary, "ok");
  armGestures();
}

/** Re-arm so a second take can be started by gesture without reloading. */
function armGestures() {
  state.startGesture.reset();
  state.stopGesture.reset();
  state.awaitingStart = state.gesturesEnabled;
  state.settleUntilMs = null;
  state.prompt = "";
  state.promptProgress = 0;
}

function onRecord() {
  // The button overrides the gesture rather than fighting it.
  if (state.recorder.recording) {
    endRecording();
    return;
  }
  if (beginRecording()) {
    state.awaitingStart = false;
    state.settleUntilMs = null;
    state.prompt = "";
    state.promptProgress = 0;
  }
}

function onDownload() {
  const name = state.recorder.download();
  if (name) setStatus(`Saved ${name} — move it into recordings/ to score it`, "ok");
}

ui.start.addEventListener("click", onStart);
ui.stop.addEventListener("click", () => stopEverything("Camera off."));
ui.record.addEventListener("click", onRecord);
ui.download.addEventListener("click", onDownload);
ui.skeleton.addEventListener("change", (event) => {
  state.showSkeleton = event.target.checked;
});
ui.gestures.addEventListener("change", (event) => {
  state.gesturesEnabled = event.target.checked;
  armGestures();
  if (!state.gesturesEnabled) {
    state.prompt = "";
    state.promptProgress = 0;
  }
});

// Release the camera however the page goes away — closing the tab, navigating
// off, or the browser discarding a backgrounded tab. Relying on the user to
// press Stop would leave the camera live and its indicator on.
window.addEventListener("pagehide", () => {
  state.running = false;
  releaseCamera();
});

// Escape stops the camera, so there is always a way out without the mouse.
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.running) {
    stopEverything("Camera off.");
  }
});
