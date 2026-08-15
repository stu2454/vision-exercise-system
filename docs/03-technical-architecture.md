# 03 — Technical Architecture & Technology Decisions

**Project:** Vision Exercise System  
**Document:** 03-technical-architecture.md  
**Status:** Revised draft v0.2  
**Date:** 15 August 2026  
**Purpose:** Define the technical architecture for the prototype and MVP, record technology decisions, and preserve the reasoning behind choices as the system evolves.

---

# 1. Purpose

This document defines the technical architecture required to implement the product concepts described in:

- `01-project-vision.md`;
- `02-clinical-product-concept.md`;
- `04-exercise-specification.md`; and
- `05-Prototype-MVP-Specification.md`.

The architecture must support two objectives that can easily conflict:

1. **make the first demonstrator fast and inexpensive to build; and**
2. **avoid creating a product that depends on a particular camera, pose model, hardware vendor or software framework.**

The system should begin on an ordinary development computer and USB camera. If the concept proves useful, it should be possible to migrate the same exercise logic to a browser, tablet, edge-AI appliance or future camera platform without rewriting the clinical movement model.

The central architecture principle remains:

> **Separate observation of movement from interpretation of movement, and interpretation from the participant-facing response.**

In practical terms:

```text
CAMERA
   ↓
POSE ESTIMATION
   ↓
CANONICAL POSE
   ↓
MOVEMENT FEATURES
   ↓
EXERCISE INTERPRETATION
   ↓
EVENTS
   ↓
FEEDBACK / DATA / UI
```

This separation is the most important defence against repeating the platform dependency that affected the Kinect generation of rehabilitation systems.

---

# 2. Architectural Goals

The architecture should make the following possible.

## 2.1 Rapid experimentation

A developer should be able to:

- open a camera;
- inspect pose output;
- record a movement;
- replay exactly the same movement;
- change an algorithm;
- compare old and new outputs;
- understand why a repetition was or was not recognised.

---

## 2.2 Replaceable sensing technology

The exercise engine must not know whether the pose originated from:

- MediaPipe;
- MoveNet;
- another pretrained pose model;
- a depth camera;
- stereo cameras;
- an edge accelerator;
- a future embedded vision platform.

---

## 2.3 Local-first operation

The initial system should operate without:

- a cloud connection;
- a user account;
- a remote API;
- continuous video upload.

Routine processing should occur locally.

---

## 2.4 Testability

Every deterministic part of the system should be testable independently.

This includes:

- coordinate transformations;
- smoothing;
- derived features;
- pose-quality decisions;
- state transitions;
- repetition counting;
- feedback rules;
- result generation.

Recorded movement streams should support reproducible integration tests.

---

## 2.5 Traceability

A session result should eventually be traceable to:

```text
application version
pose engine
pose model version
exercise specification version
exercise algorithm version
threshold configuration
camera configuration
device type
```

This is essential if measurements change as algorithms improve.

---

## 2.6 Privacy by architecture

The default production architecture should not require identifiable video to leave the participant's device or to be retained after inference.

Development recording is a separate, explicit mode.

---

## 2.7 Conservative measurement claims

The technical architecture must support the confidence framework in Document 04:

- **Level 1** — robust/product-ready measures;
- **Level 2** — useful but requiring validation;
- **Level 3** — advanced/research measures.

The architecture should never make a Level 2 or Level 3 measure appear more certain merely because the software can calculate a precise number.

---

# 3. Architectural Boundaries

The system should be divided into distinct layers.

```text
┌─────────────────────────────────────────────────────────┐
│                  PARTICIPANT EXPERIENCE                 │
│      instructions • progress • feedback • controls      │
├─────────────────────────────────────────────────────────┤
│                    FEEDBACK ENGINE                      │
│        prioritisation • rate limiting • cue rules       │
├─────────────────────────────────────────────────────────┤
│                      EVENT BUS                          │
│      rep_completed • pose_lost • safety_flag etc.       │
├─────────────────────────────────────────────────────────┤
│                   EXERCISE ENGINE                       │
│     state machines • repetition logic • task rules      │
├─────────────────────────────────────────────────────────┤
│                  MOVEMENT FEATURES                      │
│ angles • velocities • displacement • stance width       │
├─────────────────────────────────────────────────────────┤
│                POSE QUALITY + FILTERING                 │
│ confidence • smoothing • missing-data handling          │
├─────────────────────────────────────────────────────────┤
│                CANONICAL POSE ADAPTER                   │
│         vendor/model output → common pose model         │
├─────────────────────────────────────────────────────────┤
│                     POSE ENGINE                         │
│             MediaPipe initially; replaceable            │
├─────────────────────────────────────────────────────────┤
│                    FRAME SOURCE                         │
│       webcam • video file • recorded pose stream        │
└─────────────────────────────────────────────────────────┘

                    ↓ events/results

┌─────────────────────────────────────────────────────────┐
│             RECORDING / STORAGE / TESTING               │
│ JSON • SQLite • replay • annotations • regression tests │
└─────────────────────────────────────────────────────────┘
```

The key rule is:

> **Dependencies should point down the stack, never back up it.**

For example, `sit_to_stand.py` may depend on movement features but should not open the webcam, call MediaPipe directly or write SQL.

---

# 4. Prototype-to-MVP Architecture

Document 05 distinguishes the technical prototype, participant MVP and pilot product.

The architecture should evolve accordingly.

## Stage A — Pose Sandbox

```text
USB webcam
    ↓
OpenCV
    ↓
MediaPipe Pose Landmarker
    ↓
Canonical PoseFrame
    ↓
Developer overlay
    ↓
Recorder
```

Purpose:

> Determine whether useful pose data can be captured reliably in the intended environment.

---

## Stage B — Sit-to-Stand Prototype

```text
PoseFrame
    ↓
Filtering / pose quality
    ↓
Feature extraction
    ↓
STS-001 state machine
    ↓
Events
    ↓
Rep count + timing
    ↓
JSON result
```

Purpose:

> Demonstrate one reliable end-to-end movement-recognition loop.

---

## Stage C — Multi-exercise Framework

Add:

- static balance;
- weight shifting;
- stepping;
- reaching;
- marching;
- exercise configuration;
- common event schema;
- SQLite session store.

Purpose:

> Prove that new exercises can be added without changing the core sensing architecture.

---

## Stage D — Participant MVP

Add:

- participant mode;
- programme sequencing;
- spoken/text instructions;
- feedback prioritisation;
- local history;
- accessibility features.

Purpose:

> Determine whether a participant can use the system without developer assistance.

---

## Stage E — Clinician Review / Pilot Architecture

Only after the interaction loop is proven, consider:

```text
HOME DEVICE
    ↓
encrypted structured sync
    ↓
application API
    ↓
clinical data store
    ↓
provider / clinician interface
```

Cloud architecture remains deliberately deferred.

---

# 5. V0.1 Technology Decision Summary

| Area | V0.1 decision | Status | Reason |
|---|---|---|---|
| Language | Python | Accepted | Fastest route to vision experimentation |
| Camera | Commodity USB RGB webcam | Accepted | Tests monocular feasibility cheaply |
| Capture | OpenCV | Accepted | Mature and simple |
| Pose engine | MediaPipe Pose Landmarker | Accepted | Strong on-device prototype fit |
| Alternative pose engine | MoveNet | Reserved | Benchmark if MediaPipe proves limiting |
| YOLO Pose | Not core dependency | Deferred | Avoid unnecessary licensing dependency |
| Pose abstraction | Canonical PoseFrame | Accepted | Protects exercise logic from model changes |
| Filtering | Configurable simple temporal filter | Accepted | Reduce jitter without premature complexity |
| Recognition | Deterministic state machines | Accepted | Transparent, testable, explainable |
| Inter-module communication | Structured events | Accepted | Decouples exercise logic, UI and storage |
| Configuration | Versioned YAML/JSON | Accepted | Avoid scattered hard-coded thresholds |
| Session data | SQLite + JSON export | Accepted | Simple local structured storage |
| Development video | Explicit optional recording | Accepted | Enables algorithm development |
| Routine video retention | No | Accepted | Privacy-first architecture |
| Replay | Recorded video + pose-stream replay | Accepted | Essential for reproducible testing |
| Annotation | JSON/CSV ground truth | Accepted | Enables objective algorithm comparison |
| Cloud | Deferred | Accepted | Not required for core proof |
| Browser UI | Later MVP target, not V0.1 dependency | Accepted | Separate algorithm validation from deployment |
| Edge hardware | Deferred until algorithm stable | Accepted | Avoid premature hardware optimisation |
| Depth/stereo | Deferred | Accepted | Test RGB first |

---

# 6. Primary Development Language — Python

**Decision:** Python remains the V0.1 implementation language.

Python should contain the first implementation of:

- camera abstraction;
- MediaPipe adapter;
- pose models;
- filtering;
- feature extraction;
- state machines;
- recording/replay;
- annotation utilities;
- automated tests;
- local persistence.

## Why

The immediate uncertainty is movement recognition, not production deployment.

Python provides:

- rapid iteration;
- mature computer-vision tooling;
- easy numerical inspection;
- straightforward file and test tooling;
- a low barrier to algorithm experimentation.

## Architectural constraint

The exercise concepts should not become *Python-specific*.

Exercise definitions, events and stored data should use language-neutral structures such as:

- JSON;
- YAML;
- simple typed data models.

This makes later migration to TypeScript, C++, Rust or an embedded runtime more feasible.

---

# 7. Browser Strategy

Documents 04 and 05 make clear that the eventual participant experience may be browser-based.

The architecture should therefore adopt a **Python-first, browser-aware** approach.

## Prototype

Use Python to answer:

> Does the movement-recognition system actually work?

## MVP

Once exercise algorithms stabilise, evaluate a browser implementation using:

- TypeScript;
- React or a lighter equivalent;
- `getUserMedia`;
- browser-compatible local inference;
- the same canonical pose and exercise-event concepts.

## Important constraint

Do **not** build both Python and browser implementations simultaneously.

That would double work before the movement model has been validated.

The correct sequence is:

```text
prove algorithm
    ↓
stabilise interfaces
    ↓
port participant-facing runtime if justified
```

---

# 8. Camera Capture

**Decision:** OpenCV remains the initial camera abstraction.

Responsibilities:

- device enumeration where practical;
- opening the camera;
- frame capture;
- resolution configuration;
- frame timestamping;
- colour conversion;
- frame-rate monitoring;
- optional video recording.

Exercise code must never depend directly on OpenCV matrices.

A frame-source interface should make live and recorded data interchangeable.

Conceptually:

```python
class FrameSource:
    def start(self): ...
    def next_frame(self): ...
    def stop(self): ...
```

Implementations may later include:

```text
WebcamFrameSource
VideoFileFrameSource
BrowserFrameSource
DepthFrameSource
```

---

# 9. Camera Requirements

V0.1 should use an ordinary USB RGB webcam.

Initial target:

```text
resolution: 1280 × 720 or better
frame rate: ~30 fps
orientation: landscape
field of view: sufficient for whole body + exercise area
```

Do not optimise for 4K acquisition.

Higher image resolution is not automatically equivalent to better pose inference and may create unnecessary processing load.

---

# 10. Camera Position as an Experimental Variable

Document 04 explicitly leaves optimal camera orientation unresolved.

The architecture should therefore encode camera position as session metadata.

Example:

```yaml
camera:
  view: frontal_oblique
  nominal_height_cm: 100
  nominal_distance_m: 2.5
  orientation: landscape
```

Values need not initially be precise.

Sit-to-Stand should be tested from:

1. frontal;
2. approximately 30–45° oblique;
3. lateral.

The preferred view should be selected from evidence, not intuition.

---

# 11. Pose Estimation

## 11.1 Default Engine — MediaPipe Pose Landmarker

**Decision:** retain MediaPipe Pose Landmarker as the default V0.1 pose engine.

The decision is pragmatic rather than strategic.

MediaPipe should be treated as an interchangeable implementation behind the canonical adapter.

No exercise should reference:

- MediaPipe landmark indices;
- MediaPipe result objects;
- MediaPipe-specific confidence field names.

Those belong only in:

```text
pose/adapters/mediapipe_adapter.py
```

---

## 11.2 Reserved Alternative — MoveNet

MoveNet should remain the first comparison backend if testing identifies:

- unacceptable latency;
- unstable landmarks;
- deployment barriers;
- significant differences in key-joint tracking.

A benchmark should compare end-to-end exercise performance, not merely pose-model benchmark accuracy.

The useful question is:

> Which engine produces more reliable exercise events under supported home conditions?

---

## 11.3 YOLO Pose

YOLO Pose should not become a core V0.1 dependency.

It may still be useful later for:

- benchmarking;
- stronger multi-person detection;
- tracking;
- alternative embedded deployment.

Any commercial licensing decision should be made deliberately if the technical benefit justifies it.

---

# 12. Canonical Pose Model

The Canonical PoseFrame is the central technical abstraction.

An initial structure:

```python
@dataclass
class Landmark:
    x: float
    y: float
    z: float | None
    confidence: float

@dataclass
class PoseFrame:
    timestamp_ms: float
    person_confidence: float
    landmarks: dict[str, Landmark]
    source: str
```

Minimum canonical landmarks:

```text
nose

left_shoulder
right_shoulder

left_elbow
right_elbow

left_wrist
right_wrist

left_hip
right_hip

left_knee
right_knee

left_ankle
right_ankle

left_heel
right_heel

left_foot
right_foot
```

Synthetic landmarks:

```text
shoulder_centre
hip_centre
```

---

# 13. Coordinate Systems

The system should distinguish:

## Image-normalised coordinates

Usually:

```text
x ∈ [0,1]
y ∈ [0,1]
```

Use for:

- visibility;
- overlays;
- relative displacement;
- exercise-zone boundaries.

---

## Body-normalised coordinates

Measurements scaled relative to stable body dimensions.

Possible reference units:

- shoulder width;
- torso length;
- standing hip-to-ankle distance.

Use for:

- participant-relative thresholds;
- camera-distance tolerance;
- step-amplitude comparisons.

---

## World/depth coordinates

Where supplied by a pose model or future depth camera.

Use initially only as exploratory inputs.

They must not be assumed to be metrically accurate without validation.

---

# 14. Pose Quality Layer

Document 04 defines three useful operational states:

```text
GOOD
DEGRADED
INSUFFICIENT
```

This should be implemented as a separate subsystem.

Inputs may include:

- essential landmark confidence;
- percentage of required landmarks visible;
- implausible landmark jumps;
- body clipping at image boundaries;
- prolonged missing data;
- person count.

Outputs should include:

```python
PoseQuality(
    status="GOOD",
    missing_required=[],
    clipped_regions=[],
    confidence=0.91
)
```

## Behaviour

### GOOD

Exercise scoring proceeds normally.

### DEGRADED

Scoring may continue where the exercise can tolerate uncertainty, but low-confidence metrics may be suppressed.

### INSUFFICIENT

- state-machine scoring pauses;
- current partial action is not penalised;
- repositioning feedback is emitted;
- exercise resumes only after pose stabilises.

Pose quality belongs below the exercise layer so every exercise handles tracking failure consistently.

---

# 15. Temporal Filtering

Pose estimates should be filtered before feature extraction.

Initial approach:

> Use the simplest filter that materially reduces jitter without disrupting timing.

Candidates:

- exponential moving average;
- moving median;
- One Euro filter.

Filtering should be:

- configurable;
- timestamp-aware;
- testable;
- bypassable in developer mode.

Different features may require different settings.

For example:

- balance displacement may tolerate more smoothing;
- reaction-time stepping requires low latency.

---

# 16. Derived Feature Layer

State machines should consume named movement features rather than raw landmarks where possible.

Initial shared features:

```text
shoulder_centre
hip_centre
hip_height
hip_vertical_velocity

left_knee_angle
right_knee_angle
mean_knee_angle

trunk_vector
trunk_angle
trunk_lateral_displacement

stance_width

left_foot_position
right_foot_position
left_foot_velocity
right_foot_velocity

body_centre_x
body_centre_y
```

Every feature should define:

```text
name
units / coordinate basis
required landmarks
validity criteria
confidence
```

Example:

```python
FeatureValue(
    name="hip_vertical_velocity",
    value=-0.31,
    units="normalised_units_per_second",
    confidence=0.93,
    valid=True
)
```

---

# 17. Measurement Confidence Metadata

The architecture should support the confidence categories from Document 04.

A metric definition should include:

```yaml
metric:
  id: sts_rep_count
  confidence_level: 1
  status: product_ready
```

or:

```yaml
metric:
  id: sts_trunk_compensation
  confidence_level: 2
  status: exploratory
```

This metadata should travel with clinician-facing metric definitions.

It need not clutter every participant-facing result.

The purpose is governance:

> Software precision must not be confused with measurement validity.

---

# 18. Exercise Engine

Every exercise should implement a common interface.

Conceptually:

```python
class ExerciseEngine:
    def initialise(self, config, calibration): ...
    def update(self, pose, features, now): ...
    def pause(self, reason): ...
    def resume(self): ...
    def stop(self): ...
    def result(self): ...
```

Each exercise owns:

- states;
- state transitions;
- task thresholds;
- repetition logic;
- task completion logic;
- quality observations;
- exercise-specific safety events.

It does not own:

- camera;
- pose inference;
- UI;
- database;
- network connection.

---

# 19. State Machines

Deterministic state machines remain the default exercise-recognition approach.

## Sit-to-Stand

```text
SEATED
  ↓
FORWARD_PREPARATION
  ↓
RISING
  ↓
STANDING
  ↓
DESCENDING
  ↓
SEATED
```

The V0.1 implementation may omit `FORWARD_PREPARATION` if it does not improve recognition.

---

## Static Balance

```text
SETUP
  ↓
TARGET_STANCE
  ↓
HOLDING
  ├── COMPLETED
  ├── RECOVERY_STEP
  └── SUPPORT_USED
```

---

## Weight Shift

```text
CENTRE
  ↓
SHIFT_LEFT
  ↓
LEFT_TARGET
  ↓
CENTRE
  ↓
SHIFT_RIGHT
  ↓
RIGHT_TARGET
```

---

## Stepping

```text
START_STANCE
  ↓
FOOT_LIFT
  ↓
FOOT_ADVANCE
  ↓
TARGET_CONTACT
  ↓
RETURN
  ↓
START_STANCE
```

---

# 20. Hysteresis and Dwell Time

State transitions should not be triggered by a single threshold crossing.

Use:

- hysteresis;
- minimum dwell time;
- sustained movement direction;
- pose confidence.

Example:

```text
enter STANDING when height > 0.90 for ≥ N ms
leave STANDING when height < 0.80
```

Exact values must be established experimentally.

This prevents:

```text
STANDING
SEATED
STANDING
SEATED
```

oscillation caused by noisy landmarks around one threshold.

---

# 21. Calibration

Calibration should be an explicit architectural concept rather than being hidden inside exercise code.

Possible calibration data:

```text
seated_hip_height
standing_hip_height
standing_knee_angle
comfortable_stance_width
left_step_reference
right_step_reference
```

The calibration subsystem should support:

```text
session calibration
participant baseline calibration
exercise-specific calibration
```

V0.1 should prefer brief session calibration or a practice repetition.

Normative population thresholds should not be used where participant-specific references are practical.

---

# 22. Event Architecture

Document 05 introduces an event-driven product loop. This should be formalised.

Exercise logic emits events such as:

```text
participant_detected
participant_lost

pose_quality_degraded
pose_quality_insufficient
pose_quality_restored

exercise_ready
exercise_started
exercise_paused
exercise_resumed

rep_started
target_position_reached
rep_completed
partial_rep
invalid_rep

support_used
quality_flag
safety_flag

exercise_completed
exercise_stopped
```

An event may contain:

```json
{
  "event": "rep_completed",
  "timestamp_ms": 8421.44,
  "exercise_id": "STS-001",
  "sequence": 4,
  "payload": {
    "duration_seconds": 4.2
  }
}
```

The UI, storage and feedback engine subscribe to events.

They should not inspect state-machine internals directly.

---

# 23. Feedback Engine

Feedback should be a separate layer above exercise recognition.

Priority:

```text
1 SAFETY
2 TASK COMPLETION
3 LARGE MOVEMENT-QUALITY ISSUE
4 PACING
5 ENCOURAGEMENT
6 OPTIONAL PERFORMANCE INFORMATION
```

The engine should provide:

- priority resolution;
- minimum feedback interval;
- repeat suppression;
- cue expiry;
- exercise-specific enable/disable settings.

Example:

```yaml
feedback:
  min_interval_seconds: 5
  repeat_same_message: false
  encouragement: true
  movement_quality: true
```

The exercise engine should emit:

```text
rapid_descent
```

rather than directly speaking:

> “Sit down more slowly.”

This keeps clinical/interaction wording separate from movement detection.

---

# 24. Timing

All internal movement timing should use a monotonic clock.

Do not use wall-clock timestamps to calculate:

- repetition duration;
- phase duration;
- reaction time.

Wall-clock time is still useful for:

- session start;
- session end;
- record provenance.

Conceptually:

```python
monotonic_timestamp = time.perf_counter()
utc_timestamp = datetime.now(timezone.utc)
```

---

# 25. Development Recording Architecture

Recording is now considered a **core development capability**.

The recorder should support two independent outputs.

## Video recording

Purpose:

- inspect difficult examples;
- re-run pose models;
- compare alternative engines.

Format:

- ordinary local video file.

Video recording should be explicit and disabled by default outside development/testing.

---

## Pose-stream recording

Purpose:

- replay exercise logic without rerunning vision inference;
- regression-test feature and state-machine changes;
- reduce privacy exposure relative to video.

Possible format:

```json
{
  "metadata": {
    "pose_engine": "mediapipe",
    "model_version": "...",
    "fps": 30
  },
  "frames": [...]
}
```

For large recordings, JSON Lines or another efficient structured format may be preferable later.

---

# 26. Replay Architecture

The exercise pipeline should accept three interchangeable sources:

```text
LIVE CAMERA
RECORDED VIDEO
RECORDED POSE STREAM
```

This is crucial.

### Live camera

Tests full real-time system.

### Recorded video

Tests pose engine + downstream algorithms.

### Recorded pose stream

Tests filtering + features + exercise logic without pose inference variability.

A bug should be reproducible from a saved test case wherever possible.

---

# 27. Annotation

A lightweight annotation format should store human-observed ground truth.

Example:

```json
[
  {"time": 5.21, "event": "rep_started", "rep": 1},
  {"time": 6.83, "event": "standing", "rep": 1},
  {"time": 8.74, "event": "rep_completed", "rep": 1}
]
```

Annotations should be stored separately from algorithm output.

This makes possible:

```text
GROUND TRUTH
     ↓
COMPARE
     ↑
ALGORITHM OUTPUT
```

---

# 28. Regression Test Dataset

The project should maintain a small, deliberately varied development dataset.

For STS-001 include:

- normal repetitions;
- slow repetitions;
- rapid repetitions;
- partial stands;
- pauses midway;
- use of hands;
- different chairs;
- different camera views;
- lighting variation;
- occlusion;
- participant moving partially out of frame.

Each test asset should specify expected outputs.

Example:

```yaml
case_id: sts_oblique_004
true_repetitions: 8
partial_repetitions: 1
hand_support_reps: [3, 4]
camera_view: frontal_oblique
```

This dataset should become part of the project's technical intellectual property.

It should not be confused with a clinically representative validation dataset.

---

# 29. Automated Evaluation

A command-line evaluation tool should eventually produce outputs such as:

```text
Algorithm: STS 0.4.0
Dataset: STS regression set 0.2

True reps:            318
Detected correctly:   312
Missed:                 6
False positives:         2

Count agreement:      98.1%
```

Other useful measures:

- phase timing error;
- false state transitions;
- pose-loss frequency;
- hand-support classification agreement;
- processing latency.

No algorithm change should be judged solely by watching one successful demonstration.

---

# 30. Data Storage

## V0.1

Use:

- SQLite for structured sessions;
- JSON for portable debug/export artefacts.

Core entities:

```text
Participant
Session
ExerciseInstance
Trial / Repetition
Event
Metric
```

---

# 31. Suggested Data Entities

## Participant

Prototype:

```text
participant_id
display_code
created_at
```

Use synthetic identifiers during development.

---

## Session

```text
session_id
participant_id
started_at
completed_at

application_version
device_type
camera_configuration

pose_engine
pose_model_version
```

---

## Exercise Instance

```text
exercise_instance_id
session_id

exercise_id
exercise_specification_version
exercise_algorithm_version

prescribed_parameters
calibration_data

started_at
completed_at
outcome
```

---

## Trial / Repetition

```text
trial_id
exercise_instance_id
sequence

started_at_monotonic
completed_at_monotonic

classification
metrics
quality_flags
```

---

## Event

```text
event_id
exercise_instance_id
event_type
timestamp
payload
```

---

# 32. Session Output Contract

The exercise layer should return a language-neutral result.

Example:

```json
{
  "exercise_id": "STS-001",
  "exercise_specification_version": "0.1",
  "exercise_algorithm_version": "0.2.0",
  "attempted_repetitions": 10,
  "valid_repetitions": 9,
  "partial_repetitions": 1,
  "metrics": {
    "mean_rep_duration_seconds": 4.8,
    "mean_rise_time_seconds": 1.9
  },
  "quality_flags": {
    "rapid_descent": 1
  },
  "pose_quality": "adequate"
}
```

The participant UI and any future clinician interface should consume this contract rather than accessing internal objects.

---

# 33. Configuration

Parameters should be loaded from versioned configuration.

Suggested structure:

```text
config/
├── application.yaml
├── cameras/
│   └── default_usb.yaml
└── exercises/
    ├── STS-001.yaml
    ├── BAL-001.yaml
    └── STEP-001.yaml
```

An exercise definition might include:

```yaml
exercise_id: STS-001
algorithm_version: 0.2.0

required_landmarks:
  - left_hip
  - right_hip
  - left_knee
  - right_knee

pose_quality:
  minimum_confidence: 0.60

state_machine:
  minimum_dwell_ms: 200

feedback:
  repetition_count: true
  encouragement: true
  movement_quality: false
```

Threshold numbers are implementation parameters, not clinical truths.

---

# 34. Versioning

Use semantic software versioning from the beginning.

Example:

```text
application_version = 0.1.0
```

Exercise algorithms should have independent versions.

Example:

```text
STS-001 algorithm = 0.3.0
```

Exercise specifications should also have versions.

This allows distinctions such as:

```text
clinical exercise specification changed
algorithm changed
UI changed
pose engine changed
```

These are not equivalent changes.

---

# 35. Logging and Observability

Developer mode should log:

- camera frame rate;
- pose inference latency;
- processing latency;
- landmark confidence;
- pose-quality state;
- dropped frames;
- current exercise state;
- state transitions;
- feature values;
- events;
- feedback triggers;
- persistence errors.

Logs should support selectable verbosity.

Example:

```text
INFO
DEBUG
TRACE
```

Participant-facing operation should not expose technical messages.

---

# 36. Error Handling

Failures should be explicit.

Examples:

```text
CAMERA_UNAVAILABLE
POSE_ENGINE_FAILED
POSE_INSUFFICIENT
MULTIPLE_PEOPLE
STORAGE_FAILED
CONFIGURATION_INVALID
```

The participant-facing UI should translate these into simple actions.

For example:

```text
POSE_INSUFFICIENT
```

may produce:

> Move back so I can see your whole body.

The log retains the technical detail.

---

# 37. Multi-Person Handling

V0.1 supports one participant.

If multiple people are detected reliably:

```text
pause scoring
emit MULTIPLE_PEOPLE
display simple participant instruction
```

However, the architecture should distinguish:

```text
multiple people actually detected
```

from:

```text
pose model temporarily produced duplicate detections
```

This behaviour should be tested before relying on it for safety-critical logic.

---

# 38. Mobility Aids and External Objects

Walking sticks, frames, rails and chairs should not be assumed to be part of the human pose.

V0.1 may treat support use using hand/body geometry where feasible.

A future object-detection subsystem may recognise:

```text
chair
walking frame
rail
walking stick
```

but object detection should remain a separate perception layer.

Do not contaminate the canonical human pose model with object-specific assumptions.

---

# 39. Safety Architecture

The system should distinguish:

## Tracking safety

Can the system observe the task sufficiently?

Examples:

```text
feet not visible
pose lost
camera lost
participant exits frame
```

---

## Exercise safety event

Did the movement pattern indicate something requiring interruption?

Examples:

```text
rapid unexpected downward displacement
large unexpected recovery movement
repeated failed attempts
```

---

## Clinical safety

Is this exercise appropriate for this participant?

This remains outside the computer-vision architecture and belongs to prescription/professional judgement.

The MVP must not imply that accurate pose tracking guarantees exercise safety.

---

# 40. Raw Video Policy

**Routine product default:** do not retain raw video.

Development recording may be enabled explicitly.

The architecture should therefore support:

```text
camera frame
   ↓
pose inference
   ↓
frame discarded
```

while retaining:

```text
pose data / events / summary metrics
```

where required.

Any later decision to store video should be treated as a separate privacy and product decision.

---

# 41. Network and Cloud

Cloud infrastructure remains out of scope for the technical prototype.

The local system should not require internet access to:

- detect pose;
- recognise exercise;
- provide feedback;
- save a session.

Future sync should use structured session data.

Conceptual future architecture:

```text
Home Device
   ↓ HTTPS
Sync API
   ↓
Application Service
   ↓
Database
   ↓
Clinician Web App
```

The local store should queue unsynchronised sessions during outages.

---

# 42. Embedded Hardware Strategy

Hardware productisation should remain evidence-led.

## Stage A — Development computer

Use existing laptop/desktop hardware.

Purpose:

- algorithm iteration;
- debugging;
- test recording;
- model comparison.

---

## Stage B — Edge reference platform

Only after the core algorithms are stable should an edge device be selected for benchmarking.

Previously identified candidates remain:

- NVIDIA Jetson Orin Nano class hardware;
- Raspberry Pi 5 with suitable AI accelerator;
- Arduino VENTUNO Q when generally available and sufficiently mature.

The technical architecture should avoid assuming any one of these becomes the production device.

---

## Stage C — Product hardware

Select only after measuring:

- required inference throughput;
- CPU/GPU/NPU utilisation;
- memory;
- thermals;
- power;
- boot time;
- camera compatibility;
- update complexity;
- supply stability;
- commercial cost.

Headline TOPS is not a product requirement.

---

# 43. Depth / Stereo Decision

Do not introduce depth or stereo into V0.1.

First determine whether RGB pose is sufficient for:

- sit-to-stand;
- static balance;
- weight shifting;
- lateral stepping;
- reaching;
- marching.

Evaluate depth/stereo only if specific shortcomings are observed, such as:

- unreliable forward/backward displacement;
- foot-placement estimation;
- persistent occlusion;
- inadequate spatial calibration.

This keeps the decision empirical.

---

# 44. UI Architecture

V0.1 should support two modes.

## Developer Mode

Shows:

- live camera;
- pose skeleton;
- landmark confidence;
- pose-quality state;
- current exercise state;
- feature values;
- FPS;
- latency;
- emitted events.

---

## Participant Mode

Shows only:

- exercise;
- instruction;
- target;
- progress;
- one feedback cue;
- pause;
- stop.

The participant interface should never expose:

- raw confidence scores;
- state-machine names;
- joint-debug values;
- technical errors.

---

# 45. Audio Architecture

Audio should consume feedback events rather than be embedded in exercise code.

Conceptually:

```text
exercise event
    ↓
feedback engine
    ↓
message key
    ├── visual renderer
    └── speech renderer
```

Example:

```text
message key: STS_SLOW_DESCENT
```

may map to:

> Try sitting down a little more slowly.

This makes wording independently editable and supports later localisation.

---

# 46. Accessibility

Participant UI architecture should support:

- scalable text;
- high contrast;
- keyboard/touch control;
- large target areas;
- optional speech;
- no timing-dependent hover behaviour;
- generous response windows.

Accessibility is a core runtime requirement, not a later styling layer.

---

# 47. Suggested Repository Structure

```text
vision-exercise-system/
│
├── README.md
│
├── docs/
│   ├── 01-project-vision.md
│   ├── 02-clinical-product-concept.md
│   ├── 03-technical-architecture.md
│   ├── 04-exercise-specification.md
│   ├── 05-Prototype-MVP-Specification.md
│   │
│   └── decisions/
│       ├── ADR-001-mediapipe-v01.md
│       ├── ADR-002-local-video-processing.md
│       ├── ADR-003-development-hardware.md
│       ├── ADR-004-deterministic-state-machines.md
│       ├── ADR-005-local-storage.md
│       ├── ADR-006-yolo-deferred.md
│       ├── ADR-007-canonical-pose.md
│       └── ADR-008-record-replay.md
│
├── src/
│   ├── camera/
│   │   ├── base.py
│   │   ├── webcam.py
│   │   └── video_file.py
│   │
│   ├── pose/
│   │   ├── base.py
│   │   ├── models.py
│   │   ├── quality.py
│   │   └── mediapipe_adapter.py
│   │
│   ├── movement/
│   │   ├── filtering.py
│   │   ├── geometry.py
│   │   └── features.py
│   │
│   ├── exercises/
│   │   ├── base.py
│   │   ├── events.py
│   │   ├── sit_to_stand.py
│   │   ├── balance.py
│   │   ├── weight_shift.py
│   │   ├── stepping.py
│   │   ├── reaching.py
│   │   └── marching.py
│   │
│   ├── feedback/
│   │   ├── engine.py
│   │   └── messages.py
│   │
│   ├── recording/
│   │   ├── video_recorder.py
│   │   ├── pose_recorder.py
│   │   └── annotation.py
│   │
│   ├── replay/
│   │   ├── video_replay.py
│   │   └── pose_replay.py
│   │
│   ├── storage/
│   │   ├── database.py
│   │   ├── models.py
│   │   └── export.py
│   │
│   ├── ui/
│   │   ├── developer.py
│   │   └── participant.py
│   │
│   └── app.py
│
├── config/
│   ├── application.yaml
│   └── exercises/
│       ├── STS-001.yaml
│       ├── BAL-001.yaml
│       ├── BAL-002.yaml
│       ├── STEP-001.yaml
│       ├── REACH-001.yaml
│       └── STEP-002.yaml
│
├── test_data/
│   ├── README.md
│   ├── video/
│   ├── pose/
│   └── annotations/
│
├── tests/
│   ├── unit/
│   ├── replay/
│   └── regression/
│
└── tools/
    ├── annotate.py
    └── evaluate.py
```

Identifiable video must not be committed to a public repository.

---

# 48. Testing Strategy

## Unit tests

Test:

- geometry;
- normalisation;
- filtering;
- feature calculation;
- state transitions;
- event generation;
- feedback rate limiting.

---

## Replay tests

Use prerecorded pose streams to verify:

- exact repetition count;
- expected state sequence;
- expected event sequence;
- no false repetitions.

---

## Vision integration tests

Use prerecorded video to test:

```text
video
 ↓
pose
 ↓
features
 ↓
exercise engine
```

This reveals pose-engine changes that pose-stream replay cannot detect.

---

## Real-world tests

Test systematically across:

- users;
- camera views;
- lighting;
- clothing;
- chairs;
- room backgrounds;
- movement speed;
- occlusion;
- mobility aids.

---

# 49. Acceptance Metrics for STS-001

Initial engineering target under supported conditions:

```text
repetition count accuracy ≥ 95%
```

More importantly, report:

- false positive repetitions;
- missed repetitions;
- unscorable repetitions;
- pose-loss episodes;
- processing latency.

A single percentage can hide dangerous behaviour.

For example:

> 95% agreement with occasional false extra repetitions

may be less acceptable than:

> 94% agreement with conservative missed repetitions and no false positives.

The error profile matters.

---

# 50. Architecture Decision Records

Maintain ADRs in the repository.

Each should include:

```text
Title
Status
Date
Context
Options
Decision
Consequences
Conditions for revisiting
```

---

## ADR-001 — MediaPipe Pose Landmarker for V0.1

**Status:** Accepted

**Decision:** Use MediaPipe behind an adapter.

**Revisit if:** latency, landmark stability or deployment limitations materially impair exercise recognition.

---

## ADR-002 — Local video processing

**Status:** Accepted

**Decision:** routine processing local; no required video upload.

**Revisit if:** a clear product function genuinely requires remote video.

---

## ADR-003 — Development computer first

**Status:** Accepted

**Decision:** do not begin with embedded hardware.

**Reason:** movement recognition is the first uncertainty.

---

## ADR-004 — Deterministic exercise state machines

**Status:** Accepted

**Decision:** use rules/state machines before bespoke learned classifiers.

**Revisit if:** deterministic approaches fail on clearly defined movement distinctions.

---

## ADR-005 — SQLite local persistence

**Status:** Accepted

**Decision:** local structured storage plus JSON export.

---

## ADR-006 — YOLO Pose not a core dependency

**Status:** Accepted.

**Decision:** keep outside V0.1 core architecture unless technical benefit justifies later commercial/licensing analysis.

---

## ADR-007 — Canonical PoseFrame

**Status:** Accepted

**Decision:** all pose engines map to a shared vendor-neutral pose representation before exercise processing.

**Reason:** this is the key protection against platform dependency.

---

## ADR-008 — Record/replay is core infrastructure

**Status:** Accepted

**Decision:** live camera, prerecorded video and prerecorded pose streams must be usable as interchangeable test inputs.

**Reason:** movement algorithms cannot be developed rigorously without reproducible examples.

---

## ADR-009 — Structured event interface

**Status:** Accepted

**Decision:** exercise engines emit events; UI, feedback and persistence consume them.

**Reason:** separates movement interpretation from product behaviour.

---

## ADR-010 — Python-first, browser-aware

**Status:** Accepted

**Decision:** validate algorithms in Python before porting stable runtime concepts to a browser MVP.

**Reason:** avoid solving deployment before proving exercise recognition.

---

# 51. First Implementation Sequence

The previous implementation sequence is retained but expanded to incorporate the testing architecture.

## Build 0 — Camera

Deliver:

```text
Open webcam
Display frame
Display FPS
```

---

## Build 1 — Pose

Deliver:

```text
Camera
 ↓
MediaPipe
 ↓
Skeleton overlay
```

Show:

- key landmarks;
- confidence;
- inference latency.

---

## Build 2 — Canonical Pose Adapter

Deliver:

```text
MediaPipe result
 ↓
MediaPipeAdapter
 ↓
PoseFrame
```

No downstream module may consume native MediaPipe objects after this point.

---

## Build 3 — Record / Replay

Deliver:

- video recording;
- PoseFrame recording;
- video replay;
- pose-stream replay.

This should occur **before** significant exercise algorithm development.

---

## Build 4 — Pose Quality + Features

Deliver:

```text
GOOD / DEGRADED / INSUFFICIENT
```

and:

```text
hip centre
hip height
hip velocity
knee angles
trunk angle
stance width
```

---

## Build 5 — STS-001

Implement:

```text
SEATED
 ↓
RISING
 ↓
STANDING
 ↓
DESCENDING
 ↓
SEATED
```

Deliver:

- rep count;
- timings;
- events;
- JSON result.

---

## Build 6 — Ground Truth + Regression Harness

Deliver:

- manual annotation;
- expected events;
- evaluation tool;
- regression report.

Target:

> STS algorithm changes can be evaluated against the same dataset automatically.

---

## Build 7 — Participant Feedback

Deliver:

- large repetition count;
- simple positioning cue;
- completion cue;
- feedback rate limiting;
- pause;
- stop.

---

## Build 8 — Second Exercise

Implement static balance.

The second exercise is an architectural test:

> Can another exercise use the same PoseFrame, feature, event, feedback and storage infrastructure without special-case rewrites?

---

## Build 9 — Stepping / Interactive Target

Implement lateral stepping before forward/backward stepping.

This tests:

- foot tracking;
- target presentation;
- reaction timing;
- event timing;
- interactive feedback.

---

# 52. What Not to Build Yet

Do not build:

- automatic diagnosis;
- falls-risk prediction;
- AI-generated clinical advice;
- generative movement coaching;
- facial identity recognition;
- passive surveillance;
- full gait laboratory metrics;
- custom neural-network exercise classifier;
- mobile native apps;
- clinician portal;
- FHIR integration;
- provider billing;
- multi-camera reconstruction;
- production hardware enclosure;
- emergency fall-detection service.

These exclusions are architectural discipline, not statements that the capabilities have no future value.

---

# 53. Key Technical Questions to Resolve Empirically

## Pose

- How stable are hips, knees, ankles and feet across ordinary home conditions?
- Does MediaPipe remain sufficiently stable during partial occlusion?
- Is frontal-oblique STS materially more reliable than frontal or lateral?

## Timing

- What end-to-end latency occurs from movement to feedback?
- Does filtering materially distort reaction-time measures?

## Sit-to-Stand

- Can seated and standing thresholds be self-calibrated?
- How often does chair occlusion cause missed states?
- How reliably can hand support be categorised?

## Stepping

- Can lateral step magnitude be estimated robustly?
- How reliable are foot landmarks during crossover or partial occlusion?
- When does depth become necessary?

## Product

- Can camera setup be made sufficiently simple for independent use?
- Does a participant benefit from seeing their image?
- Which feedback cues help rather than distract?

---

# 54. Immediate Technical Task

The immediate task is now slightly more specific than in v0.1:

> **Create the Pose Sandbox as a Python application that opens a USB webcam, runs MediaPipe Pose Landmarker, converts its output into the Canonical PoseFrame, displays a developer overlay, and can record both the video and canonical pose stream for later replay.**

Required developer display:

```text
camera frame
skeleton
pose quality
landmark confidence
FPS
pose inference latency
recording status
```

Required controls:

```text
START CAMERA
START / STOP RECORDING
REPLAY
QUIT
```

The first important artefact is not an attractive exercise app.

It is a **repeatable movement-analysis workbench**.

---

# 55. Revised Working Architectural Position

The project should begin as a **software-defined exercise interaction system running on ordinary hardware**.

Its enduring technical assets should become:

```text
CANONICAL POSE ABSTRACTION
          +
POSE QUALITY / FILTERING
          +
MOVEMENT FEATURE LIBRARY
          +
EXERCISE STATE MACHINES
          +
EVENT MODEL
          +
FEEDBACK RULES
          +
REPLAY / REGRESSION DATASET
          +
STRUCTURED LONGITUDINAL RESULTS
```

The camera, pose engine and compute hardware should remain replaceable.

The most valuable early technical asset may not ultimately be the pose model at all.

It may be the accumulated knowledge encoded in:

- how exercises are decomposed;
- which features are sufficiently reliable;
- how uncertainty is handled;
- how movements are calibrated to the individual;
- how state transitions are made robust;
- how useful feedback is prioritised; and
- how performance is evaluated reproducibly.

That is the architecture most likely to support a commercial system that survives changes in computer-vision platforms.
