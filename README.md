# Vision Exercise System

A camera-based home exercise delivery and monitoring prototype using commodity
RGB cameras and pose estimation.

## Current phase

The **Pose Sandbox** (Builds 0–3) is implemented: camera capture, MediaPipe
pose estimation, the Canonical PoseFrame adapter, pose quality, and video and
pose-stream record and replay.

Next is Build 4 (movement features), then Build 5 (STS-001 Sit-to-Stand).

## Setup

Requires Python 3.11 or 3.12. MediaPipe does not yet publish wheels for 3.13.

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"
python tools/fetch_models.py     # downloads the pose models into models/
.venv/bin/python -m src.app check
```

`check` verifies the model, the pose engine and the camera separately, so a
failure says which one is at fault. Pass `--skip-camera` on a machine without
one. On macOS the terminal application needs camera permission before the
first live run.

## Running the sandbox

```bash
python -m src.app setup                       # camera framing check, records nothing
python -m src.app exercise                    # run STS-001 sit-to-stand live
python -m src.app score FILE.jsonl            # score a recording with STS-001
python -m src.app live                        # live webcam with developer overlay
python -m src.app replay-video FILE.mp4       # re-run pose inference over a video
python -m src.app replay-pose FILE.jsonl      # replay a pose stream, no inference
python -m src.app check                       # verify the local setup
```

`exercise` counts sit-to-stand repetitions live. Calibration comes from the
participant's own movement, so **the first sit-to-stand establishes the scale
and is not counted** — stand and sit once before the repetitions you want
scored.

`score` replays a recorded pose stream through the same engine with no pose
inference, so the same recording always gives the same result. Pass `--expect`
with a known count to check the error profile; it exits non-zero on a false
positive but not on a conservative miss (Doc 03 §49).

```bash
python -m src.app score recordings/<id>.jsonl --expect 10
```

Run `setup` before recording. It shows a large framing banner, readable from
across a room, that reads GOOD POSITION only when the whole body is in frame.
Two early development recordings were largely wasted because the legs were
below the bottom edge and there was no way to tell until afterwards.

Inspect a recording afterwards with:

```bash
python tools/inspect_recording.py recordings/<id>.jsonl
```

Keys while a window is open:

```text
r   start / stop recording
s   toggle the skeleton overlay
q   quit (Esc also works)
```

Recording writes a canonical pose stream to `recordings/<id>.jsonl`. Add
`--record-video` to capture `recordings/<id>.mp4` alongside it. Video capture
is always an explicit action and is never enabled by default.

Record the camera placement with each take — it is an open experimental
variable (Doc 03 §10), and a take that does not say where the camera was
cannot join a view comparison later:

```bash
python -m src.app live --camera-view frontal_oblique
```

Recordings open only after the frame rate has been measured, which takes about
ten frames. Cameras misreport their frame rate, and everything downstream —
video playback speed, replay timestamps, velocity features — depends on
getting it right. See the amendment in
[ADR-011](docs/decisions/ADR-011-pose-stream-format-and-timestamps.md).

`recordings/` and `models/` are gitignored. Identifiable participant video
must never be committed.

## Raspberry Pi 5

See [docs/raspberry-pi-setup.md](docs/raspberry-pi-setup.md) for the runbook and
[ADR-012](docs/decisions/ADR-012-raspberry-pi-deployment.md) for the reasoning.

Three things differ from a development machine:

- the venv needs `--system-site-packages`, because `picamera2` is an apt
  package and cannot be pip-installed;
- `camera.source` must be `picamera` for a Camera Module — OpenCV cannot open
  a CSI camera on Bookworm;
- MediaPipe is pinned to `0.10.18`, the newest release with an aarch64 wheel.

The AI HAT is not used: it cannot accelerate MediaPipe, so pose runs on the CPU
regardless. Measure before deciding otherwise:

```bash
python tools/benchmark.py --synthetic --frames 120
```

## Tests

```bash
python -m pytest              # everything
python -m pytest -m "not integration"   # skip tests that load the pose model
```

## Repository structure

```text
vision-exercise-system/
├── CLAUDE.md
├── README.md
├── docs/               project documents and decision records
├── src/
│   ├── camera/         frame sources: webcam, video file
│   ├── pose/           canonical pose model, quality, engine adapters
│   ├── recording/      pose-stream and video recorders
│   ├── replay/         video and pose-stream replay
│   ├── ui/             developer overlay
│   └── app.py          Pose Sandbox entry point
├── config/             versioned engineering parameters
├── models/             pose model bundles (fetched, not committed)
├── test_data/
├── tests/
└── tools/
```

## Start here

1. Read `CLAUDE.md`.
2. Read the project documents in `docs/`.
3. Follow the staged implementation plan in `docs/03-technical-architecture.md`.
4. Do not jump ahead to cloud, clinician portal or diagnostic features.
