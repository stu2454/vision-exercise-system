/**
 * Talks to the Python exercise engine running in a worker.
 *
 * Same interface as the HTTP bridge it replaces, so the page does not care
 * which is in use — but this one keeps the participant's movement on their own
 * device, needs no server, and runs the same Python the regression dataset
 * validates rather than a second implementation of it.
 */

const BATCH_INTERVAL_MS = 120;

export class PythonScorer {
  constructor({ onStatus, onEvent, onError, onProgress, onReady } = {}) {
    this.onStatus = onStatus || (() => {});
    this.onEvent = onEvent || (() => {});
    this.onError = onError || (() => {});
    this.onProgress = onProgress || (() => {});
    this.onReady = onReady || (() => {});
    this.worker = null;
    this.ready = false;
    this.active = false;
    this.pending = [];
    this.inFlight = false;
    this.lastSentAt = 0;
    this.nextId = 1;
    this.waiting = new Map();
  }

  /**
   * Load the engine. Slow the first time; the browser caches it after.
   *
   * `rootUrl` must be absolute and point at the repository root. A worker
   * resolves relative URLs against its own location rather than the page's,
   * so a relative base silently fetched the wrong paths.
   */
  load(rootUrl) {
    return new Promise((resolve, reject) => {
      this.worker = new Worker(new URL("web/scorer-worker.js", rootUrl));
      this.worker.onmessage = (event) => this._receive(event.data, resolve, reject);
      this.worker.onerror = (error) => {
        this.onError(`Engine failed to start: ${error.message}`);
        reject(error);
      };
      this.worker.postMessage({ type: "init", rootUrl: String(rootUrl) });
    });
  }

  _receive(data, resolve, reject) {
    if (data.type === "progress") {
      this.onProgress(data.detail);
      return;
    }
    if (data.type === "ready") {
      this.ready = true;
      this.onReady(data.version);
      resolve(data.version);
      return;
    }
    if (data.type === "error") {
      this.inFlight = false;
      this.onError(data.message);
      const waiter = this.waiting.get(data.id);
      if (waiter) {
        this.waiting.delete(data.id);
        waiter.reject(new Error(data.message));
      }
      return;
    }
    if (data.type === "status") {
      this.inFlight = false;
      this.onStatus(data.status);
      for (const event of data.status.events || []) this.onEvent(event);
      return;
    }
    const waiter = this.waiting.get(data.id);
    if (waiter) {
      this.waiting.delete(data.id);
      waiter.resolve(data);
    }
  }

  _send(message) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.waiting.set(id, { resolve, reject });
      this.worker.postMessage({ ...message, id });
    });
  }

  async start(target = null) {
    if (!this.ready) throw new Error("engine not ready");
    await this._send({ type: "start", target });
    this.pending = [];
    this.active = true;
  }

  /** Queue a frame. Sending happens on the batch interval. */
  push(pose, nowMs) {
    if (!this.active) return;
    this.pending.push(pose);
    if (this.inFlight) return;
    if (nowMs - this.lastSentAt < BATCH_INTERVAL_MS) return;
    this.lastSentAt = nowMs;
    const frames = this.pending;
    this.pending = [];
    this.inFlight = true;
    this.worker.postMessage({ type: "frames", frames, id: this.nextId++ });
  }

  async stop() {
    if (!this.active) return null;
    this.active = false;
    const data = await this._send({ type: "stop" });
    return data.result || null;
  }
}
