/**
 * Sends canonical pose frames to the Python scorer and reads back the count.
 *
 * The browser captures, runs pose estimation and draws. It does not interpret
 * movement: no filtering, no features, no calibration, no state machine. Those
 * stay in Python where the regression dataset can validate them, which is what
 * Document 03 §7 and ADR-010 ask for while the movement model is still
 * changing (calibration changed three times in two days).
 *
 * Frames are batched rather than streamed. A repetition takes around two and a
 * half seconds; a batch interval of a tenth of one is not noticeable. It would
 * not be adequate for reaction-timed games, and that difference is a reason
 * those need the algorithm settled and ported rather than bridged.
 */

const BATCH_INTERVAL_MS = 100;

export class ScoringBridge {
  constructor({ onStatus, onEvent, onError } = {}) {
    this.onStatus = onStatus || (() => {});
    this.onEvent = onEvent || (() => {});
    this.onError = onError || (() => {});
    this.sessionId = null;
    this.pending = [];
    this.inFlight = false;
    this.lastSentAt = 0;
    this.available = null;
  }

  get active() {
    return this.sessionId !== null;
  }

  async start(target = null) {
    const response = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target }),
    });
    if (!response.ok) throw new Error(`scorer refused session (${response.status})`);
    const data = await response.json();
    this.sessionId = data.session;
    this.pending = [];
    this.available = true;
    return this.sessionId;
  }

  /** Queue a frame. Sending happens on the batch interval. */
  push(pose, nowMs) {
    if (!this.sessionId) return;
    this.pending.push(pose);
    if (this.inFlight) return;
    if (nowMs - this.lastSentAt < BATCH_INTERVAL_MS) return;
    this.lastSentAt = nowMs;
    this._flush();
  }

  async _flush() {
    if (!this.sessionId || this.pending.length === 0) return;
    const frames = this.pending;
    this.pending = [];
    this.inFlight = true;
    try {
      const response = await fetch("/api/frames", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session: this.sessionId, frames }),
      });
      if (response.status === 404) {
        // The server restarted, or the session expired. Say so rather than
        // silently showing a count that has stopped advancing.
        this.sessionId = null;
        this.onError("Scoring session ended. Start recording again.");
        return;
      }
      if (!response.ok) throw new Error(`scorer error ${response.status}`);
      const data = await response.json();
      this.onStatus(data);
      for (const event of data.events || []) this.onEvent(event);
    } catch (error) {
      this.available = false;
      this.onError(`Scorer unreachable: ${error.message}`);
    } finally {
      this.inFlight = false;
    }
  }

  async stop() {
    if (!this.sessionId) return null;
    const sessionId = this.sessionId;
    await this._flush();
    this.sessionId = null;
    try {
      const response = await fetch("/api/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session: sessionId }),
      });
      if (!response.ok) return null;
      const data = await response.json();
      return data.result || null;
    } catch (error) {
      this.onError(`Could not close the scoring session: ${error.message}`);
      return null;
    }
  }
}
