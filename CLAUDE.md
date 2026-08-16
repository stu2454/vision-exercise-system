# CLAUDE.md — Vision Exercise System

## Project purpose

This repository contains the **Vision Exercise System**, a camera-based home exercise delivery and monitoring system.

The immediate goal is **not** to build a complete telerehabilitation platform.

The first goal is to determine whether a commodity RGB camera and modern pose-estimation software can support a reliable interaction loop:

```text
INSTRUCT
  ↓
OBSERVE
  ↓
RECOGNISE
  ↓
RESPOND
  ↓
RECORD
```

The first reference exercise is **Sit-to-Stand (STS-001)**.

The first major software artefact is a **Pose Sandbox / movement-analysis workbench** that:

1. opens a USB webcam;
2. runs pose estimation;
3. converts pose-model output into a canonical internal pose representation;
4. displays a developer overlay;
5. records video when explicitly requested;
6. records canonical pose streams;
7. replays recorded video;
8. replays recorded pose streams;
9. provides the basis for deterministic exercise state machines and regression testing.

---

# 1. Read the project documents first

Before implementing or materially changing architecture, read the documents in `/docs`.

These documents are the current project source of truth.

Expected files:

```text
docs/
├── 01-project-vision.md
├── 02-clinical-product-concept.md
├── 03-technical-architecture.md
├── 04-exercise-specification.md
└── 05-Prototype-MVP-Specification.md
```

If a document is absent, do not invent its content.

The documents have different roles:

## `01-project-vision.md`

Defines the overall project intent, value proposition and long-term direction.

## `02-clinical-product-concept.md`

Defines the intended rehabilitation/exercise context, user groups and product boundaries.

## `03-technical-architecture.md`

**Primary technical authority.**

Use this for:

- architecture;
- technology choices;
- module boundaries;
- data flow;
- repository structure;
- pose abstraction;
- event architecture;
- storage;
- replay;
- testing;
- technical sequencing.

## `04-exercise-specification.md`

**Primary authority for exercise semantics.**

Use this for:

- exercise IDs;
- movement states;
- clinical intent;
- repetition definitions;
- movement-quality concepts;
- safety concepts;
- progression/regression;
- measurement confidence levels.

## `05-Prototype-MVP-Specification.md`

**Primary authority for scope.**

Use this for:

- what belongs in the prototype;
- what belongs in the MVP;
- user journeys;
- participant/developer modes;
- success criteria;
- exit criteria;
- explicit non-goals.

If documents conflict, prefer the most recently revised document and flag the inconsistency before making a significant architectural change.

---

# 2. Current phase

The project is currently in:

> **Technical prototype / Pose Sandbox phase**

Do not jump ahead to:

- cloud services;
- clinician portals;
- account management;
- FHIR;
- billing;
- mobile native apps;
- production hardware;
- AI-generated coaching;
- automated clinical prescription;
- fall-risk diagnosis.

The immediate implementation sequence is:

```text
BUILD 0 — Camera
BUILD 1 — Pose
BUILD 2 — Canonical Pose Adapter
BUILD 3 — Record / Replay
BUILD 4 — Pose Quality + Features
BUILD 5 — STS-001
BUILD 6 — Ground Truth + Regression Harness
BUILD 7 — Participant Feedback
BUILD 8 — Second Exercise
BUILD 9 — Stepping / Interactive Target
```

Do not skip directly to later builds unless explicitly instructed.

---

# 3. Core architectural rule

The most important architectural rule is:

> **Separate sensing from movement interpretation, and movement interpretation from product behaviour.**

The intended pipeline is:

```text
CAMERA / VIDEO / POSE STREAM
          ↓
      POSE ENGINE
          ↓
 CANONICAL POSE ADAPTER
          ↓
POSE QUALITY + FILTERING
          ↓
   MOVEMENT FEATURES
          ↓
    EXERCISE ENGINE
          ↓
        EVENTS
       ↙   ↓   ↘
 FEEDBACK  UI  STORAGE
```

Dependencies should point down the stack.

Exercise code must not:

- open the webcam;
- import OpenCV directly;
- call MediaPipe directly;
- write SQL;
- manipulate UI widgets;
- speak feedback messages directly.

---

# 4. Technology decisions for V0.1

Use the following unless explicitly changed.

## Language

```text
Python
```

## Camera capture

```text
OpenCV
```

## Initial pose engine

```text
MediaPipe Pose Landmarker
```

MediaPipe is an implementation detail.

Do not allow MediaPipe-specific objects or landmark indices outside the MediaPipe adapter.

## Local storage

```text
SQLite
```

Use JSON for:

- exports;
- debug artefacts;
- pose recordings where practical;
- test fixtures.

## Recognition approach

Use:

```text
deterministic state machines
```

Do not introduce a bespoke neural-network exercise classifier unless deterministic logic has first been shown inadequate.

## Cloud

None for the prototype.

## Raw video

Do not retain by default.

Video recording is an explicit development/testing capability.

---

# 5. Canonical pose abstraction

All pose engines must map to a vendor-neutral canonical structure.

A starting representation:

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class Landmark:
    x: float
    y: float
    z: Optional[float]
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

Synthetic landmarks may include:

```text
shoulder_centre
hip_centre
```

No downstream module should require MediaPipe landmark numbering.

---

# 6. Frame-source abstraction

Live and recorded inputs should be interchangeable.

Conceptually:

```python
class FrameSource:
    def start(self) -> None:
        ...

    def next_frame(self):
        ...

    def stop(self) -> None:
        ...
```

Expected implementations:

```text
WebcamFrameSource
VideoFileFrameSource
```

Pose-stream replay should use a separate pose-source abstraction rather than pretending landmarks are video frames.

---

# 7. Pose quality

Implement pose quality as a shared subsystem.

Operational states:

```text
GOOD
DEGRADED
INSUFFICIENT
```

Possible inputs:

- confidence of required landmarks;
- missing landmarks;
- image-boundary clipping;
- implausible jumps;
- person missing;
- multiple people.

Expected behaviour:

## GOOD

Exercise scoring proceeds.

## DEGRADED

Exercise may continue where appropriate, but unreliable metrics should be suppressed.

## INSUFFICIENT

- pause scoring;
- emit a pose-quality event;
- do not count the incomplete action against the participant;
- allow UI/feedback layer to request repositioning;
- resume only after stable pose is restored.

Do not duplicate pose-quality handling independently inside every exercise.

---

# 8. Filtering

Do not use raw frame-by-frame landmarks directly for exercise decisions.

Begin with a simple configurable temporal filter.

Candidates:

```text
exponential moving average
moving median
One Euro filter
```

Prefer the simplest solution that removes meaningful jitter without excessive latency.

Filtering must be:

- testable;
- configurable;
- bypassable in developer mode.

---

# 9. Movement feature layer

Exercise engines should operate on named derived features rather than raw landmarks wherever possible.

Initial shared features may include:

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
```

Each feature should have explicit:

- units or coordinate basis;
- landmark requirements;
- validity criteria;
- confidence.

Do not imply metric anatomical precision where none has been validated.

---

# 10. Measurement confidence

Follow the measurement hierarchy in Document 04.

## Level 1

Robust/product-oriented measures.

Examples:

- repetition count;
- task completion;
- duration;
- step occurrence;
- gross displacement.

## Level 2

Useful but requiring validation.

Examples:

- movement asymmetry;
- trunk compensation;
- movement smoothness;
- approximate sway.

## Level 3

Advanced/research.

Examples:

- joint moments;
- ground reaction force estimates;
- diagnostic gait measures;
- fall-risk classification.

Do not promote a Level 2 or Level 3 measure into participant-facing or clinical claims merely because it is computationally available.

---

# 11. Exercise engine contract

Each exercise should implement a common conceptual interface.

Example:

```python
class ExerciseEngine:
    def initialise(self, config, calibration):
        ...

    def update(self, pose, features, now):
        ...

    def pause(self, reason):
        ...

    def resume(self):
        ...

    def stop(self):
        ...

    def result(self):
        ...
```

Exercise engines own:

- states;
- state transitions;
- repetition rules;
- task completion;
- exercise-specific quality observations;
- exercise-specific safety events.

They do not own sensing, UI, persistence or speech.

---

# 12. STS-001 reference exercise

Sit-to-Stand is the first reference implementation.

Initial state model:

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

A repetition increments only after a valid full sequence.

Potential later state:

```text
FORWARD_PREPARATION
```

Do not add it unless it improves recognition or measurement.

The earliest working STS algorithm may use primarily:

```text
hip vertical position
hip vertical velocity
```

Additional features should improve robustness, not create unnecessary complexity.

---

# 13. State-machine stability

Never trigger a state transition from one noisy frame.

Use:

- hysteresis;
- minimum dwell time;
- movement direction;
- pose confidence.

Conceptual example:

```text
enter STANDING:
    normalised height > standing_enter_threshold
    AND condition sustained for minimum dwell

leave STANDING:
    normalised height < standing_exit_threshold
```

Do not hard-code thresholds throughout Python modules.

Put configurable values in versioned exercise configuration.

---

# 14. Calibration

Prefer participant-relative calibration to fixed population thresholds.

Possible STS calibration:

```text
seated_hip_height
standing_hip_height
standing_knee_angle
```

Initial calibration may use:

- explicit setup;
- a practice repetition;
- first confirmed movement cycle.

Calibration should be represented as structured data rather than hidden local variables.

---

# 15. Event architecture

Exercise engines emit structured events.

Examples:

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

Example:

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

UI, feedback and persistence consume events.

They should not inspect state-machine internals.

---

# 16. Feedback

The feedback engine is separate from exercise recognition.

Priority:

```text
1. Safety
2. Task completion
3. Large movement-quality issue
4. Pacing
5. Encouragement
6. Optional performance information
```

Feedback should support:

- rate limiting;
- repeat suppression;
- prioritisation;
- enable/disable by exercise.

Exercise logic should emit:

```text
rapid_descent
```

not:

```text
"Try sitting down more slowly"
```

The wording belongs in the feedback layer.

---

# 17. Record and replay are core infrastructure

Do not treat recording/replay as optional debugging extras.

The system must support:

```text
LIVE CAMERA
RECORDED VIDEO
RECORDED POSE STREAM
```

Each serves a different purpose.

## Live camera

Tests real-time system.

## Recorded video

Tests:

```text
video → pose → features → exercise
```

## Recorded pose stream

Tests:

```text
pose → filtering → features → exercise
```

without pose inference variability.

The same recording should produce reproducible downstream results.

---

# 18. Development recordings

The recorder should support:

## Video

Explicit only.

Use for:

- difficult examples;
- comparing pose engines;
- visual debugging.

## Canonical pose stream

Record:

- timestamp;
- canonical landmarks;
- confidence;
- pose-quality state;
- relevant metadata.

Suggested metadata:

```text
application_version
pose_engine
pose_model_version
camera_view
nominal_resolution
recording_date
```

Do not put identifying participant names in development filenames.

---

# 19. Ground-truth annotation

Support simple manual annotations.

Example:

```json
[
  {"time": 5.21, "event": "rep_started", "rep": 1},
  {"time": 6.83, "event": "standing", "rep": 1},
  {"time": 8.74, "event": "rep_completed", "rep": 1}
]
```

Ground truth must remain separate from algorithm output.

---

# 20. Regression testing

Build a small deliberately varied STS regression dataset.

Include:

- normal repetitions;
- slow repetitions;
- fast repetitions;
- pauses;
- partial stands;
- hand support;
- different camera positions;
- chair variation;
- occlusion;
- poor lighting;
- participant partly outside frame.

Each test case should include expected outcomes.

Example:

```yaml
case_id: sts_oblique_004
true_repetitions: 8
partial_repetitions: 1
hand_support_reps:
  - 3
  - 4
camera_view: frontal_oblique
```

Algorithm changes should be evaluated against the same dataset.

Do not rely on visual impressions from one live demonstration.

---

# 21. Error profile matters

The initial engineering target for clearly visible STS repetitions is approximately:

```text
≥95% repetition count accuracy
```

However, do not optimise blindly for one percentage.

Track separately:

```text
correct repetitions
missed repetitions
false repetitions
partial repetitions
unscorable repetitions
pose-loss events
latency
```

False-positive repetitions may be more problematic than conservative missed repetitions.

---

# 22. Local persistence

Use SQLite for structured session data.

Core entities:

```text
Participant
Session
ExerciseInstance
Trial
Event
Metric
```

During early development, participant identities should be synthetic.

Example:

```text
DEV001
DEV002
```

Do not add personal data unless needed.

---

# 23. Session result contract

Exercise results should be portable structured data.

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

UI and future clinician systems should consume this output contract.

---

# 24. Configuration

Use versioned YAML or JSON.

Suggested:

```text
config/
├── application.yaml
└── exercises/
    ├── STS-001.yaml
    ├── BAL-001.yaml
    ├── BAL-002.yaml
    ├── STEP-001.yaml
    ├── REACH-001.yaml
    └── STEP-002.yaml
```

Do not scatter thresholds across Python files.

Configuration values are engineering parameters, not automatically clinical thresholds.

---

# 25. Versioning

Use semantic versioning from the beginning.

Track separately:

```text
application_version
pose_model_version
exercise_specification_version
exercise_algorithm_version
```

Persist relevant versions with every session.

---

# 26. Developer mode

The developer UI should expose:

```text
camera image
pose skeleton
pose quality
landmark confidence
current exercise state
selected feature values
FPS
pose inference latency
event log
recording status
```

Developer mode can be ugly initially.

It must be useful for understanding algorithm behaviour.

---

# 27. Participant mode

Do not optimise this until the core pose/exercise loop is stable.

When implemented, participant mode should show only:

```text
exercise name
simple instruction
target / progress
one feedback cue
pause
stop
```

Do not expose:

- confidence values;
- internal state names;
- debug angles;
- technical error strings.

---

# 28. Privacy

Default intended production behaviour:

```text
camera frame
   ↓
local inference
   ↓
pose/events/results
   ↓
frame discarded
```

Do not upload or permanently store raw video by default.

Development recording must be:

- explicit;
- visibly indicated;
- stored outside public Git history.

---

# 29. Repository structure

Use this structure unless there is a strong technical reason to refine it.

```text
vision-exercise-system/
│
├── CLAUDE.md
├── README.md
├── .gitignore
│
├── docs/
│   ├── 01-project-vision.md
│   ├── 02-clinical-product-concept.md
│   ├── 03-technical-architecture.md
│   ├── 04-exercise-specification.md
│   ├── 05-Prototype-MVP-Specification.md
│   │
│   └── decisions/
│       └── ...
│
├── src/
│   ├── camera/
│   ├── pose/
│   ├── movement/
│   ├── exercises/
│   ├── feedback/
│   ├── recording/
│   ├── replay/
│   ├── storage/
│   ├── ui/
│   └── app.py
│
├── config/
│   ├── application.yaml
│   └── exercises/
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

---

# 30. Git rules

Never commit:

- personally identifiable participant video;
- large raw recordings;
- Python virtual environments;
- API keys;
- credentials;
- generated caches;
- local SQLite databases containing participant information.

Recommended `.gitignore` entries:

```gitignore
.venv/
venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/

.env
.env.*

data/
recordings/
test_data/private_video/

*.db
*.sqlite
*.sqlite3

.DS_Store
.vscode/settings.json
```

Small synthetic test fixtures may be committed deliberately.

---

# 31. Code quality

Prefer:

- small modules;
- typed public interfaces;
- dataclasses or equivalent models;
- clear docstrings for public functions/classes;
- explicit names;
- deterministic functions;
- dependency injection where it improves testability.

Avoid:

- giant controller classes;
- global mutable state;
- hidden module-level thresholds;
- UI code mixed with computer vision;
- premature framework abstractions.

Use Python type hints.

---

# 32. Testing expectations

For each new deterministic feature:

1. add unit tests;
2. add or update replay tests where relevant;
3. run the existing test suite;
4. do not silently alter expected outputs without explaining why.

When fixing a movement-recognition bug:

1. preserve the failing recording or pose stream;
2. add it as a regression case where privacy permits;
3. create a failing test;
4. implement the fix;
5. verify that existing cases have not regressed.

---

# 33. Dependencies

Keep dependencies minimal.

Before adding a dependency, ask:

> Does this materially reduce implementation effort or improve reliability?

Avoid large infrastructure frameworks for functions that can be implemented simply.

Pin or constrain dependency versions in the project dependency file.

---

# 34. Environment

Prefer a conventional Python project using a virtual environment.

If no dependency manager has yet been selected, use one consistently rather than mixing approaches.

A reasonable initial setup can use:

```text
Python 3.11+
venv or uv
pyproject.toml
pytest
```

Do not introduce Docker unless there is a concrete development/deployment reason.

---

# 35. Current immediate task

> **Status note added 16 August 2026.** Builds 0-6 are complete: the Pose
> Sandbox, movement features, STS-001 and the regression harness all exist.
> The acceptance criteria below have been met and are retained as a record of
> what the sandbox was required to do.
>
> For the current task, read `NEXT_SESSION.md` and `docs/development-log.md`.

Unless explicitly instructed otherwise, the next implementation task is:

> **Build the Pose Sandbox.**

Minimum acceptance criteria:

## Camera

- opens default webcam;
- displays live image;
- shows FPS;
- cleanly exits.

## Pose

- runs MediaPipe Pose Landmarker;
- draws skeleton in developer mode;
- reports inference latency;
- converts all output to Canonical PoseFrame.

## Pose quality

- reports GOOD / DEGRADED / INSUFFICIENT;
- detects when the participant is not adequately visible.

## Recording

- starts/stops explicit video recording;
- records canonical pose stream;
- stores metadata.

## Replay

- replays recorded video through pose inference;
- replays pose stream independently of MediaPipe.

## Architecture

- no exercise logic depends on MediaPipe objects;
- camera source is abstracted;
- tests exist for canonical pose mapping and replay serialisation.

Do **not** implement STS-001 until this foundation is functional enough to support reproducible replay.

---

# 36. How to work on tasks

When asked to implement a feature:

1. read the relevant `/docs` sections;
2. inspect the existing code before proposing a replacement;
3. state any architectural conflict you find;
4. implement the smallest coherent change;
5. add tests;
6. run relevant tests;
7. summarise:
   - files changed;
   - behaviour added;
   - tests run;
   - known limitations;
   - sensible next step.

Do not rewrite large areas of working code merely for stylistic preference.

---

# 37. When uncertain

Prefer experimentation over unsupported assumptions.

Examples:

Do not assert:

```text
frontal-oblique is definitely the best camera view
```

Instead:

```text
implement metadata and test frontal, oblique and lateral views
```

Do not assert:

```text
a knee angle threshold of 165° defines standing
```

Instead:

```text
use participant-relative calibration and test candidate thresholds
```

Do not assert:

```text
single-camera sway equals centre-of-pressure sway
```

It does not.

Technical capability and clinical validity are separate questions.

---

# 38. Product boundary

The initial product concept is:

> **exercise delivery, adherence monitoring and movement-performance tracking**

It is not presently:

- a diagnostic system;
- a fall-risk predictor;
- a clinical decision engine;
- a replacement for professional assessment;
- an emergency monitoring service.

Protect this boundary in implementation and UI wording.

---

# 39. Guiding development principle

When choosing between:

```text
more features
```

and:

```text
better reliability, reproducibility and evidence
```

prefer the latter.

The enduring value of this project is unlikely to be the pose-estimation model itself.

The more defensible technical assets are likely to become:

- the canonical pose abstraction;
- movement feature definitions;
- exercise state models;
- calibration strategies;
- uncertainty handling;
- event architecture;
- feedback rules;
- exercise-specific datasets;
- regression tests;
- longitudinal result structures.

Build those carefully.
