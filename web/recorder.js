/**
 * Canonical pose-stream recording in the browser.
 *
 * Writes the same JSON Lines format as src/recording/pose_recorder.py: one
 * metadata object on the first line, one frame object per line after it. A
 * recording made here can be dropped into recordings/ and scored by
 * `python -m src.app score` or added to the regression dataset, which is the
 * point of matching the format rather than inventing a new one.
 *
 * Frames are held in memory and written on download. A browser cannot append
 * to a file as the Python recorder does, so a very long session would need
 * streaming to a server; for a spike this is adequate and is noted as a
 * limitation rather than hidden.
 */

import { APPLICATION_VERSION, POSE_STREAM_FORMAT_VERSION } from "./version.js";

/** Timestamped identifier carrying no participant name (CLAUDE.md §18). */
export function newRecordingId(prefix = "web") {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const stamp =
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  return `${prefix}_${stamp}`;
}

export class PoseStreamRecorder {
  constructor() {
    this.reset();
  }

  reset() {
    this.recordingId = null;
    this.metadata = null;
    this.frames = [];
    this.recording = false;
  }

  get frameCount() {
    return this.frames.length;
  }

  /**
   * Begin recording.
   *
   * `measuredFps` is required rather than optional, and the caller must have
   * measured it before calling. A camera's claimed frame rate proved wrong by
   * a factor of two during development, which would have put a silent 2x
   * error into every velocity derived from the recording. See the amendment
   * to ADR-011.
   */
  start({
    measuredFps, width, height, cameraView, poseEngine, poseModelVersion,
    trackSettings, notes,
  }) {
    this.recordingId = newRecordingId();
    this.frames = [];
    this.metadata = {
      record: "metadata",
      recording_id: this.recordingId,
      recording_date: new Date().toISOString(),
      application_version: APPLICATION_VERSION,
      pose_engine: poseEngine,
      pose_model_version: poseModelVersion,
      pose_engine_detail: `${navigator.userAgent}`,
      camera_view: cameraView || "unspecified",
      nominal_resolution: `${width}x${height}`,
      // The browser exposes no claimed rate worth trusting, so the measured
      // rate is recorded as both. Nothing downstream computes with nominal.
      nominal_fps: measuredFps,
      measured_fps: measuredFps,
      source: {
        kind: "browser_camera",
        description: "browser:getUserMedia",
        width,
        height,
        nominal_fps: measuredFps,
        measured_fps: measuredFps,
        effective_fps: measuredFps,
        user_agent: navigator.userAgent,
        // Whatever the browser will say about the camera's actual
        // configuration. The operating system may apply effects the
        // application never asked for and cannot switch off -- macOS Edge
        // Light turns the display borders into a fill light whenever the
        // camera is active, which changes the participant's illumination.
        // Anything the browser exposes about that is worth keeping with the
        // recording; what it does not expose has to be noted by hand.
        track_settings: trackSettings || null,
      },
      format_version: POSE_STREAM_FORMAT_VERSION,
      notes: notes || "",
    };
    this.recording = true;
    return this.recordingId;
  }

  write(pose) {
    if (!this.recording) return;
    this.frames.push({ record: "frame", pose });
  }

  stop() {
    this.recording = false;
    return this.recordingId;
  }

  /** The complete recording as JSON Lines text. */
  toJsonl() {
    if (!this.metadata) return "";
    const lines = [JSON.stringify(this.metadata)];
    for (const frame of this.frames) lines.push(JSON.stringify(frame));
    return lines.join("\n") + "\n";
  }

  download() {
    const text = this.toJsonl();
    if (!text) return null;
    const blob = new Blob([text], { type: "application/x-ndjson" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${this.recordingId}.jsonl`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    return `${this.recordingId}.jsonl`;
  }
}
