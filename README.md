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
python -m src.app live                        # live webcam with developer overlay
python -m src.app replay-video FILE.mp4       # re-run pose inference over a video
python -m src.app replay-pose FILE.jsonl      # replay a pose stream, no inference
python -m src.app check                       # verify the local setup
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

`recordings/` and `models/` are gitignored. Identifiable participant video
must never be committed.

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
