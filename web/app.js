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
  record: el("record"),
  download: el("download"),
  skeleton: el("skeleton"),
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
  running: false,
  startedAt: 0,
  frameIndex: 0,
  lastVideoTime: -1,
  timestamps: [],
  inferenceTimes: [],
  showSkeleton: true,
  recorder: new PoseStreamRecorder(),
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
  ui.video.srcObject = stream;
  await ui.video.play();
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
    ui.resolution.textContent = `${width}x${height}`;
  }

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
    requestAnimationFrame(loop);
  } catch (error) {
    // Say what went wrong and what to do about it.
    setStatus(`Could not start: ${error.message}`, "bad");
    ui.start.disabled = false;
  }
}

function onRecord() {
  if (state.recorder.recording) {
    const id = state.recorder.stop();
    ui.record.textContent = "Start recording";
    ui.record.classList.remove("recording");
    ui.download.disabled = false;
    setStatus(`Recorded ${state.recorder.frameCount} frames as ${id}`, "ok");
    return;
  }

  const fps = measuredFps();
  if (fps === null) {
    // Refusing rather than guessing: a wrong frame rate in the metadata is
    // the defect that cost a 2x timing error in the Python recorder.
    setStatus("Wait a moment — measuring the frame rate first.", "warn");
    return;
  }

  const id = state.recorder.start({
    measuredFps: fps,
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
}

function onDownload() {
  const name = state.recorder.download();
  if (name) setStatus(`Saved ${name} — move it into recordings/ to score it`, "ok");
}

ui.start.addEventListener("click", onStart);
ui.record.addEventListener("click", onRecord);
ui.download.addEventListener("click", onDownload);
ui.skeleton.addEventListener("change", (event) => {
  state.showSkeleton = event.target.checked;
});
