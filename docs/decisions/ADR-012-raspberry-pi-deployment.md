# ADR-012 — Raspberry Pi 5 deployment and the AI HAT

**Status:** Accepted
**Date:** 15 August 2026
**Relates to:** ADR-003 (development computer first), ADR-001 (MediaPipe for V0.1), Document 03 §42 (embedded hardware strategy), §43 (depth deferred)

---

## Context

The Raspberry Pi 5 with an AI HAT+ (Hailo-8L or Hailo-8) was raised as a
deployment target while the project is still at Stage A, the Pose Sandbox.

Document 03 §42 sequences hardware deliberately: development computer first,
edge reference platform only once algorithms are stable, product hardware only
after measurement. ADR-003 records the reason — movement recognition is the
first uncertainty, not deployment.

Investigating the target early is still worthwhile, because a deployment
constraint discovered late can invalidate architectural choices. Three
findings emerged, and two of them needed decisions.

---

## Finding 1 — the dependency pin made the Pi impossible

`mediapipe>=0.10.14,<0.11` cannot be installed on ARM64 Linux.

MediaPipe's Linux `aarch64` wheel availability is not monotonic:

| Versions | Linux aarch64 wheel |
|---|---|
| 0.10.5 – 0.10.18 | yes |
| 0.10.21 – 0.10.35 | **no** |
| 1.0.0 – 1.0.1 | yes |

The project had installed 0.10.35, which has no aarch64 wheel at all. There is
no source distribution that builds in reasonable time on a Pi.

MediaPipe 1.0.1 was evaluated as the alternative. It installs on macOS arm64
but aborts the process when creating a Pose Landmarker:

```text
F graph_service.h:139] Check failed: service_ Service is unavailable.
    @ -[DrishtiMetalHelper initWithCalculatorContext:]
    @ mediapipe::api2::TensorsToDetectionsCalculator::Open()
```

The Metal helper is initialised unconditionally in that calculator, so forcing
`Delegate.CPU` does not avoid it. MediaPipe 1.0.1 is therefore not usable on
the macOS development machine today, whatever its behaviour on Linux.

### Decision

Pin `mediapipe==0.10.18`.

It is the newest release publishing wheels for **both** `manylinux_2_17_aarch64`
and `macosx_11_0_universal2`, for CPython 3.11 and 3.12. One version therefore
covers the Pi 5 and the development machine, so both run identical inference
code and recordings stay comparable across them.

The full test suite passes on 0.10.18 on macOS arm64, including the pose
engine integration test.

### Consequences

- Pi OS Bookworm ships Python 3.11, which 0.10.18 supports.
- The pin is exact, not a range. Aarch64 availability has already lapsed once
  without warning, and a range would let a `pip install` on a Pi silently
  resolve to a version with no wheel.
- Revisit when MediaPipe 1.x is usable on macOS, or if a second pose engine
  makes the MediaPipe version less central.

---

## Finding 2 — the AI HAT cannot run MediaPipe

The Hailo-8L and Hailo-8 accelerators are reached through HailoRT and require
models compiled to HEF by the Hailo Dataflow Compiler. TFLite, which MediaPipe
uses internally, has no Hailo delegate.

Attaching the AI HAT therefore does **not** accelerate the current pose model.
`pose_landmarker_lite.task` runs on the Pi 5 CPU whether or not the HAT is
fitted.

Using the HAT for pose means a different pose engine — a Hailo pose model such
as `yolov8s_pose` from the Hailo Model Zoo. Those models emit **COCO-17**
keypoints:

```text
nose, left_eye, right_eye, left_ear, right_ear,
left_shoulder, right_shoulder, left_elbow, right_elbow,
left_wrist, right_wrist, left_hip, right_hip,
left_knee, right_knee, left_ankle, right_ankle
```

Compared with the canonical landmark set in Document 03 §12, COCO-17 cannot
supply `left_heel`, `right_heel`, `left_foot` or `right_foot`. Document 05 §13
anticipated that engines differ and asked the adapter for "the closest
canonical mapping", but four required landmarks having no source at all is a
structural gap rather than a mapping detail.

Effect by exercise:

| Exercise | Effect of COCO-17 |
|---|---|
| STS-001 Sit-to-Stand | None. Needs hips, knees, ankles, shoulders. |
| Static balance | Minor. Stance width from ankles. |
| Build 9 stepping | Degraded. Foot placement limited to ankles; no heel strike or toe position. |

### Decision

Run MediaPipe on the Pi 5 CPU first. Leave the AI HAT unused for now.

This keeps all 17 canonical landmarks, keeps one pose engine across both
machines, and follows §42: measure before selecting hardware. The measurement
tool is `tools/benchmark.py`, which reports sustained frame rate and latency
percentiles on any machine.

### Consequences

- The HAT is idle hardware until there is evidence the CPU is insufficient.
- If benchmarking shows the Pi 5 CPU cannot sustain a usable rate, the options
  in order of cost are: reduce capture resolution, keep the lite model, then
  build a Hailo adapter and accept COCO-17.
- A Hailo adapter, if built, belongs behind the canonical adapter exactly as
  MediaPipe does, and is the engine comparison Document 03 §11.2 reserves.
- Before adopting a COCO-17 engine, the pose layer should let an engine
  declare which canonical landmarks it can supply, so a missing-by-design
  landmark is reported at startup rather than as a permanent INSUFFICIENT
  pose-quality state at runtime. This is not built yet; it is not needed
  while MediaPipe is the only engine.

---

## Finding 3 — OpenCV cannot open the Pi Camera Module

On Pi OS Bookworm, CSI cameras are driven by libcamera. `cv2.VideoCapture(0)`
does not open them. A Pi with only a Camera Module attached fails at the
camera layer with the existing `WebcamFrameSource`.

### Decision

Add `PiCameraFrameSource`, using `picamera2`, selected by `camera.source` in
configuration.

### Consequences

- Nothing above the camera layer changes. This is the frame-source
  abstraction of Document 03 §8 doing the job it was introduced for.
- `picamera2` cannot be installed with pip into an isolated virtual
  environment: it depends on libcamera Python bindings distributed only as
  Debian packages. The Pi venv must be created with `--system-site-packages`.
- The libcamera format names are reversed relative to numpy channel order, so
  `RGB888` yields BGR arrays. The default is set accordingly and is
  configurable, because getting this wrong degrades pose accuracy quietly
  rather than failing loudly. It must be confirmed visually on the hardware.
- The channel order and the camera itself cannot be tested off-Pi. The frame
  handling, mirroring and lifecycle are tested with an injected camera.

---

## Conditions for revisiting

- `tools/benchmark.py` on the Pi 5 shows a sustained rate low enough to
  disrupt movement timing. Record the number before concluding anything.
- MediaPipe drops aarch64 wheels again, or becomes usable at 1.x on macOS.
- Stepping exercises (Build 9) become a priority while Hailo is also needed,
  forcing the foot-landmark trade-off to be confronted directly.
