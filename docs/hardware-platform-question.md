# Open question: deployment hardware for gamified exercise

**Status:** Unresolved. Raised 16 August 2026.
**Relates to:** Document 03 §42 (embedded hardware strategy), §53 (open technical
questions), ADR-012 (Raspberry Pi deployment), Document 05 §47 (form factors).

Document 03 §42 requires hardware selection to follow measurement rather than
intuition. This file holds the question in a form that can be put to other
people or other models, so that answers come back comparable.

Nothing here should be treated as decided. The Raspberry Pi 5 has **not yet
been benchmarked**, and until it has, every option below is speculative.

---

## The prompt

Copy everything between the rules below.

---

I am building a camera-based home exercise system for older adults and
rehabilitation participants, and I need help choosing deployment hardware. I
want evidence and reasoning, not a product listicle.

**What exists today**

A Python application that works end to end:

- Commodity USB webcam at 1280×720, ~30 fps, via OpenCV
- MediaPipe Pose Landmarker (`pose_landmarker_lite.task`, TFLite) on CPU
- A vendor-neutral canonical pose layer, so the pose engine is replaceable
- Temporal filtering, derived movement features, and a deterministic
  sit-to-stand state machine
- All processing is local. No cloud, no video retention by default.

Measured: everything downstream of pose inference costs **0.05 ms/frame**.
Pose inference is essentially the entire compute budget. It currently runs at
80 fps on an Apple M5 laptop. It has **not** been benchmarked on any
single-board computer.

**Where it is going**

Simple games that track body movement, to gamify strength and balance
exercises: on-screen targets the participant steps onto or reaches for,
reaction-timed prompts, scored balance holds. So the device must simultaneously
run pose inference, run game logic, and render graphics to a screen, within a
latency a person can feel.

**Constraints I have already established by testing**

1. The Raspberry Pi AI HAT+ (Hailo-8L / Hailo-8) **cannot accelerate
   MediaPipe** — there is no Hailo delegate for TFLite. Fitting it changes
   nothing unless I switch pose engines.
2. Hailo pose models (e.g. yolov8-pose) emit **COCO-17 keypoints, which have no
   heel or foot points**. My stepping and balance games specifically need foot
   position, so this is a significant loss, not a detail.
3. MediaPipe's Linux `aarch64` wheel availability is erratic: present to
   0.10.18, absent 0.10.21–0.10.35, restored at 1.0. MediaPipe 1.0.1 crashes on
   macOS arm64. This has already cost me a day.

**What I want from you**

Answer these, and be explicit about which parts you know versus infer:

1. **Measured throughput.** What real, sourced figures exist for MediaPipe Pose
   Landmarker (lite and full) at 720p on: Raspberry Pi 5, Intel N100/N150 mini
   PCs, NVIDIA Jetson Orin Nano Super, RK3588 boards (Orange Pi 5, Rock 5),
   and current tablets? Give the source and date. If no measurement exists for
   a platform, say so rather than estimating.

2. **Alternative pose engines that keep the feet.** Which pose models retain
   heel and toe keypoints (not just COCO-17), and which can be hardware
   accelerated on low-cost platforms? Consider MoveNet, RTMPose, YOLOv8-pose
   variants, and anything else relevant. Note licensing, since a commercial
   product is the eventual goal.

3. **Latency, not just frame rate.** For reaction-timed games, end-to-end
   camera-to-display latency matters more than average fps. What is realistically
   achievable on each platform, and what dominates it — capture, inference,
   compositing, or display?

4. **Rendering alongside inference.** Can each platform render simple 2D game
   graphics at 60 fps while running pose inference, or do they contend? Does
   using the GPU for inference make the rendering worse?

5. **The browser option.** MediaPipe Tasks for Web with WebGL or WebGPU on a
   mid-range tablet or laptop: what frame rates do people actually get, and how
   does it compare with native? This is attractive because it removes hardware
   logistics entirely, and games are easier to build there.

6. **Sustained thermal behaviour.** Exercise sessions run 20–30 minutes. Which
   of these platforms throttle under sustained inference, and by how much? A
   frame rate that drifts downward mid-session would look like an algorithm
   fault and would not be one.

7. **Total cost for home deployment.** Assume tens to low hundreds of units in
   participants' homes, each needing camera, display, audio and mounting.
   Compare buying dedicated hardware against running on a device the
   participant already owns.

**How to answer**

- Give a comparison table with a **recommendation and the reason**, not a
  ranking by TOPS. TOPS is close to irrelevant for a single pose model on one
  video stream, and I will discount any answer that leans on it.
- Distinguish clearly between measured, inferred, and unknown.
- Cite sources with dates. Flag anything you are unsure is current.
- Tell me what I should **measure myself** to settle the question, and what
  result would change the recommendation.
- If you think the premise is wrong — that I am optimising the wrong thing, or
  that the whole class of device is a mistake — say so directly.

---

## Notes for comparing the answers

Things worth checking in any reply:

- Does it acknowledge that the Pi 5 is unmeasured, or does it assume a number?
- Does it treat TOPS as meaningful for a single-stream pose model? That is a
  sign the answer is generic.
- Does it engage with the COCO-17 foot-landmark problem, which is the real
  constraint on accelerated inference?
- Does it distinguish latency from throughput?
- Are the benchmark figures sourced and dated, or asserted?
- Does it consider the browser path, or assume dedicated hardware?
