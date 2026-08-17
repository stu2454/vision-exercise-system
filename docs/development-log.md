# Development Log

**Project:** Vision Exercise System
**Period covered:** 15–17 August 2026
**Phase:** Technical prototype — Builds 0–6 complete, deployed for external testing
**Status:** STS-001 recognised end to end, 97.3% count agreement over 73 repetitions, zero false positives

This log records what was built, what broke, and what the evidence said. It is
appended to as work proceeds. Where a decision was made on evidence, the
measurement is recorded with it; where a decision was made on judgement, that
is said plainly.

---

## 1. Position at the end of this period

| | |
|---|---|
| Builds complete | 0–6 of 9 |
| Commits | 14 |
| Source | 6,481 lines |
| Tests | 3,572 lines, 348 passing |
| Regression dataset | 4 cases, 45 repetitions, one participant |
| Count agreement | 95.6% |
| False repetitions | 0 |
| Downstream processing | 0.05 ms/frame |

The engineering target in Document 03 §49 is ≥95% repetition count accuracy
with a conservative error profile. Both are currently met. **This is measured
on four takes by one participant in one room, and is not evidence that the
algorithm is good** — only that it has not regressed on what has been
recorded.

---

## 2. What was built

### Build 0–3 — Pose Sandbox

Camera capture, MediaPipe pose estimation, the canonical pose adapter, pose
quality, and record/replay.

- `src/camera/` — `FrameSource` abstraction; webcam, video file, Pi Camera
- `src/pose/` — canonical `PoseFrame`, pose quality (GOOD/DEGRADED/INSUFFICIENT)
- `src/pose/adapters/` — MediaPipe confined behind the canonical adapter
- `src/recording/` — canonical pose streams (JSON Lines) and explicit video
- `src/replay/` — video replay through inference; pose replay without it
- `src/ui/developer.py` — developer overlay

Pose-stream replay imports neither MediaPipe nor OpenCV. A test asserts this in
a subprocess, so exercise logic can never acquire a dependency on a vision
library.

### Build 4 — Filtering and movement features

- `src/movement/geometry.py` — isotropic "image heights" space
- `src/movement/filtering.py` — timestamp-aware EMA, moving median, One Euro, bypass
- `src/movement/features.py` — hip height and velocity, knee angles, trunk
  angle, stance width, each declaring units, requirements, validity and
  confidence

Filters are timestamp-aware rather than frame-counting, because measured
capture rate drifts between 27.9 and 29.9 fps within a single session.

### Build 5 — STS-001 sit-to-stand

- `src/exercises/events.py` — structured event vocabulary
- `src/exercises/base.py` — engine contract and portable result
- `src/exercises/sit_to_stand.py` — state machine, calibration, metrics
- `config/exercises/STS-001.yaml` — every threshold, none hard-coded

`SEATED → RISING → STANDING → DESCENDING → SEATED`, with hysteresis and
minimum dwell. Calibration is participant-relative, drawn from the
participant's own movement.

Knee angle is deliberately **not** used for state transitions: it corroborates
hip height well from an oblique view but is badly foreshortened frontally —
48° of range against 82° on the same participant — so depending on it would
degrade recognition at the camera angle that scores best.

### Build 6 — Ground truth and regression harness

- `test_data/regression/` — one case file per recording, ground truth kept
  separate from algorithm output
- `src/evaluation.py` — the single scoring path, shared by the `score`
  command, the evaluation tool and the regression tests
- `tools/evaluate.py` — error profile reported in parts, exits non-zero on a
  false repetition but not on a miss

### Supporting tooling

- `tools/fetch_models.py` — pose model download
- `tools/benchmark.py` — sustained frame rate and latency percentiles
- `tools/inspect_recording.py` — recording summary, quality timeline, scorable
  segments, framing diagnostics
- `python -m src.app setup` — framing check, readable from across a room
- Gesture control — one arm to start, both to finish

---

## 3. Defects found, and what they cost

The most valuable part of this record. Every one of these was found by
measurement against real recordings, not by reasoning about the code.

### 3.1 The dependency pin made the Raspberry Pi impossible

**Symptom.** `mediapipe>=0.10.14,<0.11` resolved to 0.10.35, which publishes no
Linux aarch64 wheel.

**Cause.** MediaPipe's aarch64 availability is not monotonic: present to
0.10.18, absent 0.10.21–0.10.35, restored at 1.0. MediaPipe 1.0.1 aborts on
macOS arm64 inside its Metal helper when creating a Pose Landmarker, and
forcing the CPU delegate does not avoid it.

**Fix.** Pinned exactly to `mediapipe==0.10.18`, the newest release with wheels
for both Linux aarch64 and macOS arm64.

**Recorded in** ADR-012.

### 3.2 The camera lied about its frame rate

**Symptom.** A recording reported `nominal_fps: 15.0` while frames arrived at
29.4 fps. The same camera reported 30.0 in a later session.

**Cost.** ADR-011 made replayed video timestamps derive from the file's frame
rate, so a wrong rate would have put a silent 2× error into every velocity
feature computed from replay. Recorded video would also have played at half
speed.

**Fix.** Frame sources measure their own delivered rate and always prefer it.
Recordings open only once a rate has been measured. Verified: container rate
within 0.7% of truth, replayed duration within 0.7% of the live segment.
Trusting the claim would have given 100% error.

### 3.3 Aspect ratio — my own error, twice

**Symptom.** Estimating camera view from normalised shoulder width gave a
shoulder-to-torso ratio of 0.47 and the conclusion "every take is oblique".

**Cause.** Canonical landmarks divide x by image width and y by image height.
On 1280×720 that compresses horizontal distances by 0.5625. Corrected, the same
takes gave 0.83–0.88, which is anatomically ordinary, and only one take was
actually oblique.

**Fix.** `src/movement/geometry.py` works in isotropic image heights. I made
this error a second time in an ad-hoc analysis *after* building the module
designed to prevent it.

### 3.4 Calibration was contaminated by everything that was not exercise

**Symptom.** A live session counted **zero** repetitions.

**Cause.** Three compounding faults.

1. Hip height in image units depends on distance from the camera, so crossing
   the room moves it further than a repetition does. The 5th–95th percentile
   spread was 0.247 against a true repetition travel of 0.137, so repetitions
   reached only 0.55 of the calibrated range and never crossed the standing
   threshold.
2. Calibration drew on the whole session, so fifteen seconds spent elsewhere in
   the room became the seated reference.
3. Refinement was skipped during a repetition, but a repetition that reaches
   standing under bad calibration never descends far enough to complete — so it
   stayed in flight forever, blocking the refinement that would have fixed the
   calibration that caused it.

**Fix.** Cluster-based calibration (Otsu split, cluster medians) instead of
percentiles; a trailing ten-second window; history discarded after a tracking
loss longer than a second; repetitions expire after `maximum_rep_seconds`.

**Also tried and rejected**, with measurements:

| Candidate | Result |
|---|---|
| Hip elevation above ankles, in torso lengths | Inflated worse: 0.798 vs 0.295–0.408. Perspective changes the hip-to-ankle relationship as the participant approaches. |
| Torso length as a distance proxy | Varies 60% during clean repetitions alone, because the trunk leans forward when seated. |
| Cluster medians | 0.116–0.145 across four recordings, against percentile spreads of 0.130–0.247. Adopted. |

### 3.5 The gesture holds were longer than a person actually holds

**Symptom.** The stop gesture failed twice.

**Measurements.** Both arms held for **1.49 s** against a 1.50 s threshold;
then **1.00 s** against a 1.00 s threshold. Each time the participant gave up
and reached for the keyboard — the exact thing the gesture exists to avoid.

**Cause of the bad threshold.** I reasoned that a stop firing by accident ends
the attempt, so it should demand more deliberation than a start. The
measurements say the deliberateness comes from the gesture itself: both arms
raised together qualified accidentally for 0.06 s across a 118-second session
and not at all across a 77-second one.

**Fix.** Inverted. One arm is the weaker signal, so the **start** carries the
longer hold: 800 ms to start, 600 ms to stop.

### 3.6 `rapid_descent` measured the wrong thing

**Symptom.** Flagged 11 of 12 repetitions in a session of deliberately *slow*
sit-to-stands, where descents ran 0.23–1.60 s. It had flagged nearly every
repetition of every session.

**Cause.** An absolute 0.5 s threshold. Descent speed is confounded by how
quickly a given person moves.

**Fix.** Participant-relative, like calibration: below 60% of that
participant's own median descent, with a 0.20 s absolute floor. Now fires zero
times across all recordings — correct, as none contains an outlier — and tests
cover both directions, because a flag that never fires is as useless as one
that always does.

The measure remains **Level 2**: computable, not validated.

### 3.7 Replay did not reproduce the live run

**Symptom.** A gesture-delimited recording scored differently from the session
that produced it.

**Cause.** `score` did not apply the gesture gate.

**Fix.** Scoring moved to `src/evaluation.py`, shared by the command, the
evaluation tool and the regression tests. Gestures are recovered from the pose
stream itself, so no recording format change was needed.

### 3.8 The operating system was changing the lighting

**Symptom.** A bright rounded-rectangle halo appeared around the browser window
whenever the camera started, and vanished when it stopped.

**Not the application.** The halo covered Safari's own toolbar and extended
past the page on every side, and CSS cannot paint outside the viewport. I
misidentified it twice from a photograph before that reasoning settled it.

**Cause.** **macOS Edge Light** — a recent feature that turns the display
borders into a virtual ring light whenever any application activates the
camera. Applied by the operating system, never requested by the application.

**Why it matters.** The participant's illumination stops being independent of
the application. Lighting becomes a function of whether our software is
running, which is exactly the variable a home-environment test is supposed to
hold still. The same applies to Centre Stage, Studio Light and background
blur; Centre Stage is the worst of them, because it pans and crops the frame
during movement, which is indistinguishable from the participant moving and
would corrupt participant-relative calibration.

**Response.** Effects off while developing and recording. The browser recorder
now stores `MediaStreamTrack.getSettings()` in the metadata, which captures
what the browser will admit about the camera — it does not report Edge Light,
so this is partial. Added to `docs/failure-conditions.md`, and no recording
made so far records whether Edge Light was active.

### 3.9 Process failure: a mangled command polluted the repository

Shell commands were given with trailing `# comments`. Interactive zsh does not
treat `#` as a comment, so `python3.12 -m venv .venv  # stdlib venv includes
pip` created six directories, and `git add -A` swept 1,752 files into a pushed
commit. Cleaned by rebuilding the commit from the working tree and
force-pushing. **Inline comments are no longer used inside command blocks.**

---

## 4. What the measurements say

### Regression dataset

```
case                      view               true  det  miss  false
sts_frontal_001           frontal              12   11     1      0
sts_gesture_001           frontal              11   11     0      0
sts_oblique_001           oblique_66           10    9     1      0
sts_slow_001              frontal              12   12     0      0

True repetitions:         45
Detected correctly:       43
Missed:                    2
False positives:           0
Count agreement:        95.6%
```

Both remaining misses are calibration repetitions in recordings made before the
start gesture existed. Neither gesture-delimited recording loses any.

### Camera view — an open question, with first evidence

| | Frontal | Oblique ~66° |
|---|---|---|
| Scorable frames | 92% | 81% |
| Ankle confidence | 0.97 | 0.75 |
| Knee angle range | 48° | 82° |
| Seated knee angle | ~130° | ~88–93° |

Frontal wins on scorability and ankle confidence. The oblique view measures
knee flexion far more truthfully — ~90° is anatomically correct for sitting, so
the frontal view's ~130° is foreshortening, not anatomy. Not a conclusion: one
participant, one session, and the oblique take also had worse framing.

### Recalled counts are not ground truth

Wrong twice, in opposite directions. Reported 10 where evidence showed 12;
reported 11 where it was 12, having not counted the first repetition. A
disputed count is not recorded until resolved.

### Browser runtime — measured 17 August 2026

A browser spike (`web/`) running the **same** `pose_landmarker_lite.task` file
as the Python application, on the same M5 laptop:

| | Python | Browser |
|---|---|---|
| Inference | 10.6 ms | **13.3 ms** |
| Sustained rate | 80 fps | **59.9 fps** |

The 59.9 is the display's 60 Hz refresh capping `requestAnimationFrame`, not a
limit of the runtime: 13.3 ms implies roughly 75 fps of headroom. The browser
is around 25% slower at inference than native Python and still well above the
30 fps capture target.

This materially improves the case for the browser deployment path in Document
03 §7 and ADR-010, and correspondingly weakens the case for buying dedicated
inference hardware. It does not settle it — the figure is one machine, and the
Raspberry Pi 5 remains unbenchmarked.

Measured with only the head and shoulders in frame, so person confidence was
0.24 and not comparable with a full-body take. Inference time is largely
independent of that; the frame rate figure is the one to trust here.

### Raspberry Pi 5 with AI HAT

The Hailo accelerator **cannot run MediaPipe** — there is no Hailo delegate for
TFLite, so pose runs on the CPU whether or not the HAT is fitted. Using it
means a Hailo pose model emitting COCO-17 keypoints, which cannot supply
`left_heel`, `right_heel`, `left_foot` or `right_foot`. STS-001 is unaffected;
Build 9 stepping would be degraded to ankles.

Decision: MediaPipe on CPU first, HAT idle, per ADR-003 and Document 03 §42.
`tools/benchmark.py` provides the measurement that would justify changing it.
Reference figure: an Apple M5 sustains 80 fps on synthetic 1280×720.

---

## 5. Decisions recorded

| ADR | Subject |
|---|---|
| 001–010 | Established in Document 03 before implementation |
| **011** | Pose-stream format (JSON Lines) and replay timestamps, amended after the frame-rate defect |
| **012** | Raspberry Pi 5 deployment, the MediaPipe pin, and why the AI HAT is unused |

---

## 6. Known limitations

**The dataset is thin.** Four takes, one participant, one room, all clean. Doc
03 §28 asks for slow and fast repetitions, pauses mid-movement, partial stands,
hand support, chair variation, occlusion, poor lighting, a participant partly
out of frame, and more than one person. Only speed variation exists so far.

**Calibration costs the first repetition** in recordings without a start
gesture. Persisting calibration between sessions would reclaim it.

**Recovery from bad calibration is slow** — it waits for the stalled repetition
to expire. Shortening that would speed recovery and start rejecting genuinely
slow repetitions, which is the wrong trade for frailer participants.

**`pose_quality` in results reports the worst status across the whole take**,
including walk-in, so it reads pessimistically.

**Multi-person handling is off** (`num_poses=1`). Distinguishing a genuine
second person from a duplicate detection needs testing before anything depends
on it.

**The Pi Camera path is untested on hardware.** Frame handling, mirroring and
lifecycle are tested with an injected camera; the channel order cannot be
confirmed off-Pi.

**Nothing here is clinically validated.** Repetition count is Level 1. Trunk
angle, knee angle and asymmetry are Level 2 at best — computable, not
validated.

---

## 7. Next

Agreed direction: **deliberately awkward and failed attempts**, especially
patterns an older adult would produce — hesitation, partial stands, pushing up
off the thighs, pauses, sitting heavily, using an armrest.

The dataset gets more valuable the more the recordings differ, and cases the
algorithm handles *badly* are the ones that show where thresholds are still
wrong. `--record-video` on those takes would also make disputed counts
decidable by watching rather than by inference.

Then Build 7 — participant feedback — built on thresholds that have been
stress-tested rather than on ones that have only seen clean movement.

---

## 8. Working principles that have earned their place

1. **Measure, don't reason, about thresholds.** Every threshold set by
   judgement in this period was wrong when measured: 1.50 s, 1.00 s, 0.5 s.
2. **Prefer a conservative miss to a false positive.** Held throughout; the
   dataset has zero false repetitions.
3. **Record and replay everything.** Every defect in §3 was diagnosed by
   replaying a recording, not by watching a live demonstration.
4. **Ground truth is separate from algorithm output**, and human memory is not
   ground truth.
5. **Say what has not been shown.** A number measured on four takes by one
   person is reported as exactly that.

---

# Day 3 — 17 August 2026

Two threads: putting the system in front of someone else, and the awkward
recordings that the previous day's plan called for. The awkward recordings
found more than everything before them combined.

## 9. The browser

### 9.1 A spike, not a port

`web/` runs pose estimation in a browser and stops there. No filtering,
features or state machine: Document 03 §7 and ADR-010 are explicit that the two
implementations must not be built at once while the movement model is still
changing. A test fails if the exercise thresholds appear in the JavaScript, so
the boundary is enforced rather than remembered.

Measured on the same laptop, same model file:

| | Python | Browser |
|---|---|---|
| Inference | 10.6 ms | 13.3 ms |
| Sustained | 80 fps | 59.9 fps (display-capped) |

The browser also negotiates far higher capture rates than OpenCV does — up to
**74.8 fps** against 30 — which turned out to matter (§10.1).

### 9.2 Recordings are interchangeable

The browser writes the same JSON Lines format as the Python recorder, and both
runtimes load the identical model file, so a difference between them is the
runtime rather than the model. `tests/unit/test_web_parity.py` reads the
JavaScript as text and compares the landmark map, the gesture thresholds and
the version constants against the Python source of truth.

## 10. Defects found by the awkward recordings

### 10.1 The calibration window was measured in frames

300 frames is ten seconds at 30 fps and **four** at the 74.8 fps the browser
negotiated. A participant held standing for 11.8 seconds, which emptied the
window of every seated sample. The cluster split then separated standing from
standing and calibrated travel collapsed from 0.114 to 0.040, after which any
half-hearted rise cleared the standing threshold.

The same defect class as frame-counting filters, which were made
timestamp-aware for exactly this reason. The lesson had been applied to
filtering and features and not to calibration.

Fixed: the window is in seconds, and an estimate is rejected unless each
cluster holds at least a fifth of it.

### 10.2 Touching standing height is not achieving it

Across 43 confirmed-genuine repetitions the shortest standing time was
**1.00 s**. An abandoned stand held for **0.30 s** and was counted. A
repetition now requires standing to be held for `minimum_standing_seconds`,
default 0.4 s, sitting between the two with margin either side.

### 10.3 Calibration that adapts cannot detect what it adapts to

The most important finding of the three days.

Ten full repetitions reached a hip height of 0.434. Four deliberately
incomplete rises reached 0.380 — a real, measurable difference. But calibration
had by then re-learned standing as **0.373**, so every incomplete rise measured
as *above* full standing and all four were counted.

The reference was following the movement down. **That is the wrong direction
for a rehabilitation measure**: a participant whose stands get shallower
through fatigue should produce partial repetitions, not have the bar quietly
lowered to meet them.

Calibration now freezes after three completed repetitions. A tracking loss long
enough to suggest the participant has moved still discards it and starts again,
which is the legitimate reason to recalibrate.

### 10.4 The operating system was changing the lighting

**macOS Edge Light** turns the display borders into a ring light whenever any
application activates the camera. Applied by the operating system, never
requested. The participant's illumination therefore stops being independent of
the application, which is the variable a home-environment test is meant to hold
still. Centre Stage would be worse — it pans and crops during movement, which
is indistinguishable from the participant moving.

Recorded in `docs/failure-conditions.md`. We cannot detect these from inside
the application, and no recording made before the discovery notes whether they
were active.

## 11. A suspicion retired, and a distinction learned

**Pausing mid-rise was expected to fail.** Rising is confirmed by upward
velocity, so a pause looked likely to stop RISING being entered at all. All
four paused repetitions were detected, with rise times of 6.5, 3.5, 2.0 and
1.6 s: the check only gates *entering* the state, which a slow rise still
satisfies. A documented weakness removed by measurement rather than left as a
warning.

**The engine counts movements, not intentions.** A participant stood up twice
to finish and switch the machine off, and those were first recorded as
repetitions on the grounds that the engine could not know the difference. Raw
hip height said otherwise — 0.482 and 0.464 against 0.528 for the exercise
repetitions. Rising to walk away is not a sit-to-stand. Ground truth for that
case was revised from 16 to 14, with the measurement recorded beside it.

## 12. Deployment for external testing

<https://stu2454.github.io/vision-exercise-system/web/try/>

Participant mode (Document 05 §8, CLAUDE.md §27): introduction, instructions,
then camera with positioning guidance in plain language, a large repetition
count and one cue at a time. No frame rates, confidences, state names or
technical errors.

**The repetition counting is the project's own Python, running in the
browser.** The whole scoring path turned out to be pure Python — no numpy, no
OpenCV, no MediaPipe — so Pyodide executes the real modules under WebAssembly.
One exercise engine, validated by the regression dataset, with nothing leaving
the participant's device. A test asserts that path stays free of compiled
dependencies, because one such import would force the second implementation
this avoids.

The file list is generated by walking imports, and verified by copying only
those files into an empty directory and scoring a real recording there: 14
repetitions and 5 partials, matching the full application exactly.

Cost: **13 MB on the first visit**, almost all of it the Python runtime. Our own
code is 131 KB. Cached afterwards.

### 12.1 Three faults that only appeared in a browser

- A grid list wrapped to one word per line, because a three-child item
  auto-placed its third child into a 2.2 rem column.
- The worker fetched `/python-manifest.json` rather than
  `/web/python-manifest.json`. A worker resolves relative URLs against its own
  location, not the page's.
- That failure was invisible: the boot panel reported progress but never
  failure, so a 404 looked identical to a slow load.

All three were found by the participant running the page, none by the 385
tests. **Nothing in this project verifies that the browser page executes**,
which is now the largest untested surface.

## 13. Position at the end of day 3

| Measure | Standing |
|---|---|
| Tests | 385 |
| Regression dataset | 6 cases, 73 repetitions, one participant |
| Count agreement | 97.3% |
| False repetitions | 0 |
| Failure conditions tested | 6 of ~30 |

Both remaining misses are calibration repetitions in recordings made before the
start gesture existed.

## 14. Next

**Single leg stance, timed, with and without eyes closed.**

This is Build 8, and its purpose in the sequence is architectural rather than
clinical: *can a second exercise use the same canonical pose, feature, event
and storage infrastructure without special-case rewrites?* If it needs the core
changed, the abstraction is not carrying its weight.

Points to settle before building:

- It is a **timed hold**, not a repetition count, so the result contract and
  the state model both differ from STS-001. Document 03 §19 sketches
  `SETUP → TARGET_STANCE → HOLDING → COMPLETED / RECOVERY_STEP / SUPPORT_USED`.
- **Eyes closed is probably not observable.** Face landmarks at 2–3 m are
  unlikely to support eyelid state reliably, and MediaPipe Pose carries no
  eyelid detail at all. It may have to be a protocol instruction recorded as
  metadata rather than something detected — and if so, the system must not
  imply it verified it.
- The interesting measurements are Level 2 at best: sway amplitude from a
  single camera is **not** centre-of-pressure sway (CLAUDE.md §37).
- Recovery steps and reaching for support are the events that matter
  clinically, and neither is currently detectable.

Also outstanding: hand support and armrest use remain untested for STS-001, and
the browser page has no automated verification at all.
