# Browser Pose Sandbox

A **spike, not a port.** It answers one question — does pose estimation run
acceptably in a browser, on this machine and on a tablet? — and stops at pose.

No filtering, no movement features, no state machine, no exercise logic. Those
stay in Python. Document 03 §7 and ADR-010 are explicit that the two
implementations must not be built simultaneously, because that doubles the work
before the movement model has been validated. A test in
`tests/unit/test_web_parity.py` fails if exercise-engine names appear here, so
the spike cannot quietly become a port.

## Running it

`getUserMedia` needs `localhost` or https, so it will not work by opening the
file directly. Serve the repository root, not this directory — the page loads
the pose model from `../models/`.

```bash
cd ~/dev/vision-exercise-system
source .venv/bin/activate
python -m http.server 8000
```

Then open <http://localhost:8000/web/>.

To try it on a tablet on the same network, find your machine's address with
`ipconfig getifaddr en0` and open `http://<address>:8000/web/` — but note that
most browsers refuse camera access over plain http to anything except
`localhost`, so a tablet test needs https or a tunnel.

## Stopping the camera

**Stop camera** releases it immediately — every media track is stopped, the
indicator light goes out and the picture is cleared. **Escape** does the same,
so there is always a way out without the mouse. Closing the tab or navigating
away also releases it, via `pagehide`.

Pausing the video element or dropping its reference is not enough on its own:
the camera stays live and its light stays on. Everything that ends a session
routes through one teardown path for that reason.

A recording in progress is stopped but kept, and stays downloadable. Silently
discarding someone's take would be worse than ending it early.

## What it shows

Frames per second, mean inference time, person confidence, landmark count and
capture resolution — the same figures the Python developer overlay reports, so
the two can be compared directly.

## Recordings are interchangeable with Python

The download button writes a canonical pose stream in the **same JSON Lines
format** as `src/recording/pose_recorder.py`. Move it into `recordings/` and
the existing tooling works on it unchanged:

```bash
python tools/inspect_recording.py recordings/web_<id>.jsonl
python -m src.app score recordings/web_<id>.jsonl --no-start-gesture
```

Pass `--no-start-gesture` unless you actually performed the arm-raise — the
gesture is recovered from the pose stream itself, so it works either way.

## Why the comparison is meaningful

Both runtimes load the **identical** `models/pose_landmarker_lite.task` file.
Any difference between a browser recording and a Python recording of the same
movement is therefore the runtime, not the model.

The frame is mirrored before inference, matching `WebcamFrameSource(mirror=True)`,
so canonical left and right mean the same thing in both.

## Keeping the two in step

`canonical.js` restates the landmark names, the MediaPipe index map and the
synthetic midpoints in JavaScript. Two implementations of one definition drift.
`tests/unit/test_web_parity.py` reads this JavaScript as text and compares it
with the Python source of truth, so drift fails the suite rather than being
discovered later in a comparison that quietly means nothing.

If you change `src/pose/models.py` or the MediaPipe adapter's index map, expect
that test to tell you to change this too.

## Known limitations

- Frames are held in memory until download. A long session would need
  streaming to a server; adequate for a spike.
- The WASM runtime is loaded from a CDN, so the page needs internet access on
  first load. The pose model itself is served locally.
- GPU delegate is requested. If a device lacks WebGL support the runtime falls
  back, and the frame rate figure will reflect that — worth noting when
  comparing devices.
