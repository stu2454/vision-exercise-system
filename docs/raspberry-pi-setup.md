# Raspberry Pi 5 setup

A practical runbook for running the Pose Sandbox on a Raspberry Pi 5 with a
Camera Module. The reasoning behind these choices is in
[ADR-012](decisions/ADR-012-raspberry-pi-deployment.md).

**The AI HAT is not used.** It cannot accelerate MediaPipe, so pose runs on the
Pi 5 CPU whether or not the HAT is fitted. Measure the CPU first; see
[Benchmark](#4-benchmark-before-anything-else) below.

---

## 0. Assumptions

```text
Raspberry Pi 5
Raspberry Pi OS Bookworm, 64-bit      (arm64 — the 32-bit image will not work)
Raspberry Pi Camera Module via CSI
Python 3.11                            (ships with Bookworm)
```

Confirm the architecture before starting. A 32-bit userland has no MediaPipe
wheel:

```bash
uname -m          # must print aarch64
```

---

## 1. System packages

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-venv git
```

`python3-picamera2` brings the libcamera Python bindings. These are **not**
available from pip — that is why the virtual environment below is not
isolated.

Check the camera is detected before going further:

```bash
rpicam-hello --list-cameras
```

If no camera is listed, stop and fix that first. Nothing downstream will work.

---

## 2. Virtual environment

```bash
git clone https://github.com/stu2454/vision-exercise-system.git
cd vision-exercise-system

python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

`--system-site-packages` is required. Without it the venv cannot see
picamera2, and the camera will fail to open with an error saying exactly this.

The pinned `mediapipe==0.10.18` is the newest version with an `aarch64` wheel;
0.10.21 through 0.10.35 have none and would try to build from source. Do not
"upgrade to latest" here without reading ADR-012.

---

## 3. Configuration

Edit `config/application.yaml`:

```yaml
camera:
  source: picamera        # was: webcam
  width: 1280
  height: 720
  fps: 30
  view: frontal_oblique   # record what you actually set up
```

Then verify the whole setup:

```bash
python -m src.app check
```

Expect:

```text
  platform        Linux aarch64 python 3.11.x
  pose model      OK    pose_landmarker_lite.task
  pose engine     OK    mediapipe
  camera          OK    picamera:csi 1280x720 @ 30 fps
```

Download the pose models first if the model line says MISSING:

```bash
python tools/fetch_models.py
```

---

## 4. Benchmark before anything else

This is the number that decides whether the AI HAT is needed at all.

```bash
python tools/benchmark.py --synthetic --frames 120
```

Better, use a real recording containing a person — detecting nobody is cheaper
than tracking somebody, so synthetic figures are an upper bound:

```bash
python tools/benchmark.py recordings/dev_20260815_120000.mp4
```

Reference figure: an Apple M5 development machine sustains **80 fps** on
synthetic 1280×720 with `pose_landmarker_lite.task`. The Pi 5 will be
substantially slower. What matters is the sustained rate:

| Sustained rate | Interpretation |
|---|---|
| ≥ 30 fps | At the capture target. Nothing to do. |
| 15–30 fps | Usable for sit-to-stand. Velocity features get coarser. |
| < 15 fps | Try 960×540 capture before concluding the HAT is required. |

Record the result. Hardware decisions should follow measurements, not
impressions (Document 03 §42).

---

## 5. Running headless

The developer overlay needs a display. Over SSH with no monitor, use
`--headless`:

```bash
python -m src.app live --headless --max-frames 300 --record
```

That still runs the full pipeline and writes a pose stream; it just draws
nothing. With a monitor attached, or over SSH with X forwarding, drop the flag
to get the overlay and the `r` / `s` / `q` keys.

---

## 6. Known issues

### Colours look wrong — skin appears blue

The libcamera format names are reversed relative to numpy channel order. Set:

```yaml
camera:
  picamera_format: BGR888
```

Worth checking deliberately: swapped channels degrade pose accuracy quietly
rather than failing outright. Record a few seconds and look at the video.

### Camera fails with "picamera2 is not available"

The venv was created without `--system-site-packages`. Recreate it:

```bash
rm -rf .venv
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### pip tries to build MediaPipe from source

The architecture is not `aarch64`, or Python is not 3.11/3.12. Check both:

```bash
uname -m
python3 --version
```

### Thermals

Sustained pose inference loads all four cores. Use a case with a fan or a
heatsink; a throttled Pi produces a frame rate that drifts downward during a
session, which looks like an algorithm problem and is not one.

---

## 7. What is deliberately not set up

- **The AI HAT / Hailo accelerator.** See ADR-012. Using it means a different
  pose model with COCO-17 keypoints, which has no heel or foot landmarks.
- **Autostart on boot, kiosk mode, remote access.** These belong to Phase 5
  (feasibility pilot build), not to the Pose Sandbox.
- **USB webcam on the Pi.** Supported — set `source: webcam` — but the Camera
  Module was the chosen configuration.
