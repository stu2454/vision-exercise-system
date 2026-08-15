# 05 — Prototype / MVP Specification

**Project:** Vision Exercise System  
**Document:** 05-Prototype-MVP-Specification.md  
**Status:** Draft v0.1  
**Purpose:** Define the smallest credible prototype and minimum viable product for a camera-based home exercise delivery and monitoring system.

---

# 1. Purpose

The purpose of the first prototype is not to build a complete telerehabilitation platform.

It is to answer a narrower question:

> Can a commodity camera and modern pose-estimation software reliably support a simple, usable home exercise experience in which a participant follows an exercise, the system recognises the movement, counts performance, provides limited feedback, and produces a useful session record?

The first prototype should establish whether the core technical and product assumptions are sound before significant effort is invested in:

- clinical workflow integration;
- large exercise libraries;
- sophisticated analytics;
- remote clinician dashboards;
- regulatory claims;
- automated prescription;
- full production infrastructure.

The central design principle is therefore:

> **Prove the interaction loop before building the platform.**

That interaction loop is:

```text
SELECT EXERCISE
      ↓
SET UP CAMERA
      ↓
CONFIRM PARTICIPANT POSITION
      ↓
SHOW INSTRUCTION
      ↓
OBSERVE MOVEMENT
      ↓
DETECT PERFORMANCE
      ↓
GIVE MINIMAL FEEDBACK
      ↓
COMPLETE EXERCISE
      ↓
GENERATE SESSION SUMMARY
```

---

# 2. Prototype, MVP and Pilot Product

The terms **prototype**, **MVP** and **pilot product** should be kept distinct.

## 2.1 Prototype

The prototype is a developer-operated system used to test technical feasibility.

It may:

- run locally;
- require manual setup;
- use hard-coded exercise parameters;
- store files locally;
- expose debug information;
- tolerate an unattractive user interface;
- require manual review of results.

Its purpose is learning, not deployment.

---

## 2.2 Minimum Viable Product

The MVP is the smallest version that a real participant could use with minimal assistance.

It should:

- have a coherent user interface;
- support a small exercise programme;
- guide camera setup;
- recover from common errors;
- record sessions consistently;
- provide a simple summary;
- be installable or accessible without developer intervention.

The MVP still does not need to be a fully commercial clinical product.

---

## 2.3 Pilot Product

A pilot product is suitable for limited use with selected participants and professionals under a defined protocol.

It introduces requirements that the MVP may not initially need, including:

- user accounts;
- data security;
- privacy documentation;
- remote review;
- auditability;
- controlled software versions;
- technical support;
- monitoring of failures;
- formal safety processes.

The project should avoid prematurely imposing pilot-product requirements on the earliest technical prototype.

---

# 3. Core Product Hypothesis

The initial hypothesis is:

> A participant can undertake a prescribed set of functional strength, balance and stepping exercises in their home using a standard camera-equipped computing device, while the system uses pose estimation to recognise gross movement performance and provide simple feedback without requiring wearable sensors or an instrumented mat.

This hypothesis contains several assumptions that need to be tested independently.

### Technical assumptions

1. Pose estimation is sufficiently stable in a typical home.
2. Relevant body regions remain visible during selected exercises.
3. Exercise states can be recognised using relatively simple logic.
4. Repetition counts and timed tasks can be measured reliably.
5. Performance can be processed with acceptable latency.

### Human factors assumptions

1. Older adults can position themselves appropriately relative to the camera.
2. Instructions can be understood without continuous human supervision.
3. Visual or auditory feedback does not interfere with exercise performance.
4. Participants tolerate camera-based monitoring.
5. Setup burden is not excessive.

### Product assumptions

1. Exercise delivery plus objective performance monitoring is useful enough to justify adoption.
2. Clinicians value concise session information rather than raw pose data.
3. A small set of well-supported exercises is more valuable initially than a large poorly measured library.
4. Commodity hardware materially lowers deployment friction compared with bespoke sensing systems.

The MVP programme should generate evidence against these assumptions rather than treating them as established facts.

---

# 4. MVP Scope

The MVP should support one complete exercise session comprising approximately three to six exercises.

Recommended initial exercise set:

1. Sit-to-Stand
2. Static Standing Balance
3. Side-to-Side Weight Shift
4. Forward or Lateral Target Step
5. Standing Reach
6. Marching in Place

The first engineering implementation should still begin with **Sit-to-Stand only**.

---

# 5. Primary User

The primary MVP user is:

> An independently living older adult or rehabilitation participant who has already been prescribed an appropriate exercise programme.

This definition is deliberate.

The MVP is **not** initially intended to decide:

- whether the person should exercise;
- what diagnosis they have;
- whether they are at risk of falling;
- which exercise is clinically appropriate;
- whether they require medical assessment.

Those functions remain outside the first product boundary.

---

# 6. Secondary User

The likely secondary user is:

> A physiotherapist, exercise physiologist, allied health professional or supervised assistant who wants to review whether the participant completed the programme and obtain a small number of meaningful performance indicators.

The clinician-facing experience should therefore focus on summary information rather than a live stream of biomechanical data.

---

# 7. Initial User Journey

## 7.1 Launch

Participant opens the Vision Exercise application.

The home screen should show a very small number of choices.

For the prototype:

```text
VISION EXERCISE

Today's Exercise

[ Start Session ]

[ Camera Check ]

[ Previous Session ]
```

The interface should avoid dashboards, menus and configuration options that are unnecessary to the participant.

---

## 7.2 Camera check

Before exercise begins, the system displays the camera view.

The participant receives a simple positioning instruction such as:

> Stand where your whole body is visible.

The system should determine whether essential body landmarks are visible.

Possible status indicator:

```text
● Move back slightly
● Good position
```

The system should not display technical pose-confidence values.

---

## 7.3 Environment check

For exercises requiring a chair, the participant should be instructed to position a stable chair.

The MVP does not necessarily need automatic chair recognition.

Instead:

> Place a stable chair behind you, then select Continue.

The system may eventually identify obvious chair position, but this is not required for V0.1.

---

## 7.4 Exercise introduction

Each exercise should show:

- exercise name;
- simple visual demonstration;
- one sentence instruction;
- target repetitions or duration;
- Start button.

Example:

```text
SIT TO STAND

Stand all the way up,
then sit back down with control.

Target: 8 repetitions

[ Start ]
```

---

## 7.5 Exercise performance

During the exercise, the participant should see only information that assists performance.

Recommended display:

```text
            [ simplified avatar / camera view ]

                      4 / 8

                 Good — keep going
```

Optional:

- large countdown timer;
- target graphic;
- pause button;
- stop button.

Debug landmarks and technical overlays should be available only in developer mode.

---

## 7.6 Exercise completion

At the end of the exercise:

```text
Exercise complete

8 of 8 repetitions

Average time: 4.6 s

[ Continue ]
```

Do not overwhelm the participant with movement-quality metrics.

---

## 7.7 Session completion

At the end of the session:

```text
Session complete

5 exercises completed
27 minutes

Great work.

[ Done ]
```

A clinician-facing summary can contain additional measures.

---

# 8. Prototype User Modes

The software should support at least two modes.

## Participant Mode

Characteristics:

- simplified interface;
- full-screen;
- minimal controls;
- no debugging information;
- large text and buttons;
- sparse feedback.

## Developer Mode

Characteristics:

- pose skeleton overlay;
- state-machine state;
- landmark confidence;
- calculated features;
- event log;
- frame rate;
- model latency;
- manual event annotation;
- recording controls.

Developer Mode is essential during early algorithm development.

---

# 9. Sit-to-Stand Reference Prototype

Sit-to-Stand should be the first complete implementation.

## 9.1 Minimum behaviour

The system must:

1. detect that a participant is visible;
2. recognise a stable seated state;
3. recognise rising;
4. recognise standing;
5. recognise descent;
6. recognise return to seated position;
7. increment the repetition counter;
8. display the count;
9. record timestamps;
10. save a session result.

---

## 9.2 Prototype state machine

```text
NO_PERSON
    ↓
READY
    ↓
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

A repetition increments only when the sequence:

```text
SEATED → RISING → STANDING → DESCENDING → SEATED
```

has been completed.

---

## 9.3 Minimum measured features

For the first STS implementation:

- hip vertical position;
- knee angle estimate;
- trunk orientation;
- landmark confidence;
- elapsed time;
- movement direction.

Only hip vertical displacement may be required for the earliest successful algorithm.

The additional features should initially be used to improve robustness rather than increase product claims.

---

# 10. Minimum Feedback Engine

The feedback engine should initially use deterministic rules.

Example categories:

### Encouragement

Triggered periodically:

- “Good.”
- “Keep going.”
- “Well done.”

### Completion prompt

If standing threshold is not reached:

- “Stand a little taller.”

### Pacing

If descent is repeatedly very rapid:

- “Try sitting down more slowly.”

### Positioning

If pose confidence falls:

- “Move back so I can see your whole body.”

### Safety

If a potentially unsafe event occurs:

- “Stop and steady yourself.”

The first prototype should not attempt generative conversational coaching during movement.

---

# 11. Feedback Rate Limiting

The system should prevent repeated instructions.

Possible rule:

```text
minimum_feedback_interval = 5 seconds
```

Additional rules:

- do not repeat identical feedback consecutively;
- suppress quality feedback immediately after safety feedback;
- allow encouragement even when no correction is required;
- disable selected feedback categories per exercise.

---

# 12. Pose Estimation Layer

The MVP architecture should abstract the pose engine from the exercise logic.

Conceptual pipeline:

```text
CAMERA
  ↓
POSE ENGINE
  ↓
CANONICAL LANDMARK MODEL
  ↓
FILTERING
  ↓
DERIVED FEATURES
  ↓
EXERCISE STATE MACHINE
  ↓
EVENTS
  ↓
FEEDBACK + DATA STORE
```

This allows the underlying pose technology to change without rewriting every exercise specification.

---

# 13. Canonical Landmark Model

The initial canonical skeleton should include at least:

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

Derived synthetic landmarks may include:

```text
shoulder_centre
hip_centre
trunk_vector
```

Not every pose engine will expose exactly the same points.

The adapter layer should provide the closest canonical mapping.

---

# 14. Pose Data Object

An internal pose frame might be represented as:

```json
{
  "timestamp": 1723700000.123,
  "landmarks": {
    "left_hip": {
      "x": 0.43,
      "y": 0.55,
      "z": -0.10,
      "confidence": 0.96
    },
    "right_hip": {
      "x": 0.57,
      "y": 0.55,
      "z": -0.09,
      "confidence": 0.95
    }
  }
}
```

Coordinates should ideally be normalised relative to frame dimensions.

Raw camera pixels should not be embedded directly throughout exercise logic.

---

# 15. Temporal Filtering

Raw pose data should not be used directly.

Possible approaches include:

- moving average;
- exponential smoothing;
- median filter;
- Kalman filtering.

The first prototype should favour the simplest technique that removes obvious jitter without introducing unacceptable latency.

The filtering method should be configurable because different derived measures may require different smoothing.

---

# 16. Event Architecture

Exercise logic should emit discrete events.

Examples:

```text
participant_detected
participant_lost
exercise_ready
rep_started
standing_reached
rep_completed
partial_rep
support_used
quality_flag
safety_flag
exercise_completed
```

This event-driven structure will make it easier to connect:

- scoring;
- audio;
- user interface;
- logging;
- remote analytics.

---

# 17. Exercise Configuration Object

Exercises should preferably be loaded from configuration rather than being fully hard-coded.

Example:

```yaml
exercise:
  id: STS-001
  name: Sit to Stand
  target_repetitions: 8

camera:
  preferred_view: frontal_oblique

feedback:
  repetition_count: true
  encouragement: true
  quality_feedback: true

thresholds:
  minimum_landmark_confidence: 0.6
  state_dwell_ms: 200
```

Thresholds shown here are illustrative only.

They should be determined empirically.

---

# 18. Technology Approach

The first prototype should maximise speed of experimentation.

A reasonable development architecture is:

```text
Browser / desktop UI
        ↓
Local camera stream
        ↓
Pose estimation
        ↓
Exercise engine
        ↓
Local session store
```

The earliest version does not require cloud infrastructure.

Potential implementation options include:

### Browser-first

Advantages:

- no installation;
- easy deployment;
- camera APIs readily available;
- potentially easier future distribution.

Disadvantages:

- browser performance differences;
- pose-model compatibility;
- local file access limitations.

### Python desktop prototype

Advantages:

- rapid experimentation;
- strong computer-vision ecosystem;
- easy data inspection;
- convenient offline development.

Disadvantages:

- less representative of eventual participant deployment;
- packaging can become awkward;
- user interface development is less straightforward.

### Hybrid approach

A productive path may be:

1. develop and validate pose/exercise logic in Python;
2. replicate stable logic in a browser application;
3. retain recorded pose streams for reproducible algorithm testing.

This reduces pressure to solve UI deployment before basic movement recognition works.

---

# 19. Recommended Prototype Development Stack

The exact technology decision belongs in the Technical Architecture document, but the prototype should ideally contain:

### Pose experimentation

- Python
- OpenCV
- a current pose-estimation framework
- NumPy
- Pandas where useful

### Algorithm testing

- recorded video playback;
- saved pose landmark streams;
- manually annotated ground truth;
- automated comparison scripts.

### MVP interface

Likely:

- TypeScript;
- React or a similarly lightweight browser framework;
- WebRTC/getUserMedia camera access;
- browser-compatible pose inference where feasible.

The project should not become dependent on a large infrastructure framework before the core interaction has been validated.

---

# 20. Recording and Replay Tool

A pose recorder/replay utility should be considered a core development tool.

It should allow a developer to:

1. record camera video;
2. optionally record pose landmarks;
3. replay the same movement repeatedly;
4. run revised algorithms against identical data;
5. compare expected and detected events.

This avoids repeatedly performing exercises during code development.

It also allows algorithm versions to be compared objectively.

---

# 21. Manual Annotation

Recorded test sessions should support simple ground-truth annotation.

Example:

```text
00:05.21 rep_start
00:06.83 standing
00:08.74 seated
00:08.74 rep_complete
```

Automated output can then be compared with manually observed events.

A lightweight annotation format such as CSV or JSON is sufficient.

---

# 22. MVP Data Model

The MVP should store three broad levels of data.

## Participant-level

Minimal prototype fields:

```text
participant_id
display_name
configuration
```

Personally identifying data should be avoided wherever it is not required.

---

## Session-level

```text
session_id
participant_id
start_time
end_time
exercise_programme
device_information
software_version
```

---

## Exercise-level

```text
exercise_id
exercise_version
target
attempts
valid_repetitions
duration
metrics
quality_flags
safety_flags
pose_quality
```

---

# 23. Raw Video Storage

Raw video should **not** automatically be considered necessary for the commercial system.

The prototype may use recorded video during development.

For routine participant use, alternatives include:

- process video locally and discard it;
- retain only derived pose landmarks;
- retain summary metrics only;
- allow explicit temporary diagnostic recording.

This decision has significant implications for:

- privacy;
- storage;
- consent;
- bandwidth;
- security;
- participant acceptability.

A default architecture that does not need to transmit or permanently store identifiable video may be commercially advantageous.

---

# 24. Session Summary

The participant-facing summary should be intentionally simple.

Example:

```text
TODAY

Sit to Stand
8 / 8 completed

Balance
30 seconds completed

Stepping
10 / 10 completed

Session complete
```

The clinician-facing version might show:

```text
Sit to Stand
8/8 valid
Mean rep duration: 4.6 s
Hand support: 2 reps
Rapid descent flag: 1 rep

Static balance
Target: 30 s
Completed: 27 s
Recovery steps: 1
```

---

# 25. Longitudinal Display

Longitudinal tracking is desirable for the MVP, but it should remain simple.

Possible display:

```text
Sit-to-Stand

Average repetition time

Week 1   5.3 s
Week 2   5.0 s
Week 3   4.8 s
Week 4   4.7 s
```

Trend visualisation should initially favour easily interpreted variables.

The system should avoid presenting changes as clinically meaningful unless that interpretation has evidence behind it.

---

# 26. Remote Clinician Review

Remote review is not necessary for the first technical prototype.

For the MVP, two possible approaches exist.

## Option A — Local export

Generate:

- JSON;
- CSV;
- PDF summary.

Advantages:

- simple;
- avoids cloud infrastructure;
- useful during trials.

## Option B — Basic cloud synchronisation

Upload structured session summaries to a clinician dashboard.

Advantages:

- closer to intended telerehabilitation workflow;
- enables remote monitoring.

Disadvantages:

- authentication;
- privacy;
- hosting;
- security;
- permissions;
- operational support.

The recommended sequence is **local export first**, then cloud synchronisation once the core exercise interaction works.

---

# 27. MVP Safety Model

The system should distinguish between:

### Exercise safety instructions

Defined by the exercise.

Example:

> Keep a stable bench beside you.

### Observable safety events

Events the camera may potentially detect.

Example:

- rapid unexpected downward movement;
- participant leaves frame suddenly;
- repeated incomplete transfer.

### Emergency response

The MVP should **not** claim to be a personal emergency response system.

A computer vision exercise application cannot guarantee that a fall or medical emergency will be detected.

Any future emergency-monitoring functionality should be treated as a separate product capability with separate evidence and design requirements.

---

# 28. Pause and Stop

Every participant exercise screen should contain obvious controls for:

```text
PAUSE

STOP
```

The application should also recognise an optional spoken stop command where technically straightforward.

No exercise should require completion once started.

---

# 29. Accessibility Requirements

The MVP interface should be designed for older users from the beginning.

Minimum requirements:

- large text;
- large clickable controls;
- strong contrast;
- uncluttered screens;
- no dependence on hover behaviour;
- simple language;
- audio reinforcement where useful;
- generous time to respond;
- no rapidly disappearing instructions.

Accessibility should be treated as core product design, not later cosmetic work.

---

# 30. Audio

Audio feedback can reduce the need for participants to look continually at the screen.

The MVP should support:

- spoken exercise instruction;
- repetition count if enabled;
- brief corrective cue;
- encouragement;
- completion cue.

Audio should be optional.

---

# 31. Visual Representation

Three visual approaches should be tested.

## Camera image

Participant sees themselves.

Advantages:

- intuitive;
- assists positioning.

Potential disadvantage:

- some users dislike watching themselves.

## Skeleton overlay

Advantages:

- demonstrates that the system sees movement.

Potential disadvantages:

- technically distracting;
- may appear clinical or surveillance-oriented.

## Avatar

Advantages:

- potentially more engaging;
- can simplify visual information.

Disadvantages:

- additional implementation effort;
- may introduce latency or uncanny movement.

The first prototype should use the **camera image with optional skeleton overlay in developer mode**.

---

# 32. Gamification

The MVP should use game mechanics cautiously.

Potential useful elements:

- progress bar;
- target count;
- stepping targets;
- completion streak;
- simple achievement feedback.

Avoid initially:

- complex scoring;
- leaderboards;
- competitive ranking;
- childish graphics;
- reward systems disconnected from therapeutic goals.

The experience should feel motivating without trivialising rehabilitation.

---

# 33. Target Interaction

Stepping and reaching exercises provide the clearest opportunity for interactive visual targets.

Example:

```text
          ●

    ●           ●

          YOU
```

A target can appear and the participant responds by:

- stepping;
- reaching;
- shifting weight.

This creates a bridge between the project's earlier exergaming concepts and modern camera-based exercise delivery without requiring a pressure-sensitive mat.

---

# 34. Programme Representation

A programme should be represented as a sequence of exercise configurations.

Example:

```yaml
programme:
  id: DEMO-001
  name: Basic Balance and Strength

  exercises:

    - id: STS-001
      repetitions: 8
      sets: 2

    - id: BAL-001
      variant: feet_together
      duration_seconds: 30

    - id: STEP-001
      direction: lateral
      repetitions: 10
```

The participant should not need to configure these settings themselves.

---

# 35. MVP Success Criteria

The project should define explicit criteria before adding functionality.

## Technical

For Sit-to-Stand under supported conditions:

- repetition count is correct for at least 95% of clearly visible repetitions;
- false repetitions are rare;
- state recognition remains stable despite moderate pose jitter;
- feedback latency is not disruptive;
- temporary landmark loss does not corrupt the session;
- session data is saved consistently.

These values are initial engineering targets, not validated clinical thresholds.

---

## Usability

A participant should be able to:

- understand where to stand;
- begin an exercise;
- understand the primary instruction;
- know how many repetitions remain;
- pause or stop;
- understand when the exercise is complete.

The interaction should not require understanding computer vision.

---

## Product

At least one rehabilitation professional should be able to review a session summary and answer:

- Did the participant complete the prescribed exercise?
- How much did they complete?
- Did they use support?
- Was there an obvious performance issue worth reviewing?
- Has performance changed across sessions?

If the data cannot support these basic questions, adding more measurements is unlikely to solve the core product problem.

---

# 36. Prototype Exit Criteria

The project can move from STS technical prototype to multi-exercise MVP once:

1. Sit-to-Stand works reliably across multiple recorded users;
2. the same recording produces reproducible results;
3. camera setup requirements are understood;
4. pose failure modes have been documented;
5. session results can be saved and replayed;
6. basic participant feedback works;
7. the exercise engine is sufficiently modular to add a second exercise without rewriting the application.

---

# 37. MVP Exit Criteria

The MVP may be considered ready for a small supervised feasibility pilot when:

1. at least four exercise types work reliably;
2. participants can complete the workflow without developer assistance;
3. camera setup errors are handled gracefully;
4. sessions are consistently recorded;
5. privacy behaviour is defined;
6. data can be exported or reviewed;
7. software versions are controlled;
8. known failure modes are documented;
9. a basic safety and risk assessment exists;
10. professional users judge the outputs understandable and potentially useful.

---

# 38. Explicit Non-Goals for MVP

The following should be excluded unless new evidence makes them essential.

### Not in MVP

- automated diagnosis;
- automated falls-risk classification;
- gait laboratory replacement;
- autonomous exercise prescription;
- AI-generated clinical advice;
- integration with electronic medical records;
- billing systems;
- NDIS integration;
- aged-care management systems;
- wearable sensor integration;
- force plates;
- pressure mats;
- multi-camera 3D reconstruction;
- detailed skeletal biomechanics;
- virtual reality headset support;
- social networking;
- competitive leaderboards;
- continuous passive monitoring;
- emergency fall-detection service.

These may be reconsidered later.

---

# 39. Failure Modes to Test Deliberately

The prototype should actively test failure rather than only ideal demonstrations.

Test cases should include:

- participant too close to camera;
- participant too far away;
- head outside frame;
- feet outside frame;
- poor lighting;
- strong backlight;
- patterned clothing;
- dark clothing;
- chair partially obscuring legs;
- participant turning sideways;
- participant using hands;
- walking frame present;
- another person entering frame;
- pet entering frame;
- participant stopping halfway;
- participant performing extra movements;
- camera moved during session;
- slow internet where cloud components exist.

The system's response to failure may be more important than marginal improvements in ideal-condition pose accuracy.

---

# 40. Prototype Test Dataset

A small internal dataset should be created during development.

For Sit-to-Stand, capture variations in:

- participant;
- chair height;
- camera angle;
- camera distance;
- lighting;
- movement speed;
- use of hands;
- partial stands;
- failed attempts.

Each recording should have manual annotation.

This becomes the project's first regression test set.

---

# 41. Algorithm Regression Testing

Each algorithm update should run automatically against the stored dataset.

Example report:

```text
STS algorithm v0.3

Videos tested: 42
True repetitions: 318

Correctly detected: 312
Missed: 6
False positives: 2

Count accuracy: 98.1%
```

Performance should be tracked by software version.

This is more valuable than relying on developer impressions.

---

# 42. Logging

The prototype should log enough information to understand failures.

Recommended log events:

```text
application_started
camera_started
pose_started
pose_lost
exercise_started
state_changed
feedback_triggered
rep_completed
exercise_stopped
exercise_completed
application_error
```

Debug logs should not become part of the participant-facing record.

---

# 43. Software Versioning

Every recorded session should include:

```text
application_version
pose_model_version
exercise_definition_version
```

Without this, longitudinal comparisons may become difficult when algorithms change.

---

# 44. Privacy-by-Design Decisions

Even during prototyping, architecture should avoid unnecessary collection.

Preferred principles:

- process video locally where practical;
- do not retain raw video by default;
- assign non-identifying participant IDs;
- store only information needed for the intended function;
- make recording explicit;
- separate development recordings from participant data;
- document where data is processed.

These choices will reduce later redesign.

---

# 45. Regulatory Boundary

The first commercial concept should be framed conservatively around:

> exercise delivery, adherence monitoring and performance tracking.

Claims such as:

- predicts falls;
- diagnoses impairment;
- determines safe exercise prescription;
- detects clinical deterioration;
- replaces professional assessment;

could materially change evidence and regulatory obligations.

Product language should therefore evolve alongside the evidence base rather than preceding it.

---

# 46. Commercial Learning Goals

The prototype should answer not only technical questions but commercial ones.

Questions to investigate:

- Who is willing to pay?
- Is the value primarily to the participant, provider or clinician?
- Is monitoring more valuable than exercise content?
- Does camera-based measurement improve adherence?
- How often would professionals actually review the data?
- Which metrics change a clinical decision?
- Is installation/setup support required?
- What hardware do target participants already own?
- Would providers prefer tablet-based deployment?
- Is local processing a meaningful privacy differentiator?

These questions should be tested early enough to influence architecture.

---

# 47. Possible Initial Commercial Form Factors

## Consumer tablet

A preconfigured tablet placed in the participant's home.

Advantages:

- controlled camera and screen;
- simplified support;
- predictable performance.

Disadvantages:

- hardware logistics;
- cost;
- charging and maintenance.

---

## Participant's own tablet/laptop

Advantages:

- low hardware cost;
- easy scale.

Disadvantages:

- variable devices;
- variable camera quality;
- support burden.

---

## Smart television / external camera

Potentially compelling longer term for older users.

Disadvantages:

- fragmented platform;
- difficult browser/camera access;
- development complexity.

For early pilots, a **known tablet or laptop configuration** is likely to reduce technical variability.

---

# 48. Development Phases

## Phase 0 — Pose Sandbox

Deliverables:

- live camera;
- pose overlay;
- landmark logging;
- video recording;
- replay.

Exit question:

> Can we obtain stable enough pose data in the intended environment?

---

## Phase 1 — Sit-to-Stand Engine

Deliverables:

- STS state machine;
- rep counting;
- timing;
- simple feedback;
- automated test dataset.

Exit question:

> Can we recognise one useful exercise reliably?

---

## Phase 2 — Exercise Framework

Add:

- configuration-driven exercises;
- common event model;
- session recording;
- static balance;
- stepping.

Exit question:

> Can the architecture support different movement types cleanly?

---

## Phase 3 — Participant MVP

Add:

- participant interface;
- programme flow;
- audio instructions;
- setup guidance;
- exercise summary;
- local history.

Exit question:

> Can somebody use it without a developer standing beside them?

---

## Phase 4 — Clinician Review

Add:

- structured export;
- longitudinal display;
- simple clinician summary.

Exit question:

> Is the captured information useful to someone supervising rehabilitation remotely?

---

## Phase 5 — Feasibility Pilot Build

Add only what is necessary for controlled field deployment:

- account management;
- security controls;
- privacy process;
- remote synchronisation if required;
- error monitoring;
- software release controls.

Exit question:

> Is there enough evidence of technical usability and professional value to justify a formal pilot?

---

# 49. Suggested First Repository Structure

A possible initial repository could be:

```text
vision-exercise-system/

├── README.md
├── docs/
│   ├── 01-project-vision.md
│   ├── 02-clinical-product-concept.md
│   ├── 03-technical-architecture.md
│   ├── 04-exercise-specification.md
│   └── 05-prototype-mvp-specification.md
│
├── prototype/
│   ├── camera/
│   ├── pose/
│   ├── exercises/
│   │   └── sit_to_stand/
│   ├── recording/
│   ├── replay/
│   └── ui/
│
├── exercise_definitions/
│   └── STS-001.yaml
│
├── test_data/
│   ├── videos/
│   ├── pose/
│   └── annotations/
│
└── tests/
    └── sit_to_stand/
```

Raw videos containing identifiable people should generally not be committed to a public Git repository.

---

# 50. First Build Backlog

The first practical development backlog should be small.

## Milestone A — See the participant

- open webcam;
- run pose estimation;
- draw skeleton;
- show frame rate;
- report landmark confidence.

## Milestone B — Record and replay

- record short video;
- save pose landmarks;
- replay video;
- replay pose data.

## Milestone C — Detect posture

- calculate hip centre;
- determine seated state;
- determine standing state;
- display current state.

## Milestone D — Detect repetitions

- implement STS state machine;
- count repetitions;
- prevent double counts;
- handle partial repetitions.

## Milestone E — Feedback

- participant-mode interface;
- spoken/text repetition count;
- positioning prompt;
- basic encouragement.

## Milestone F — Save results

- session ID;
- exercise result;
- timestamps;
- rep count;
- rep timing;
- JSON output.

At that point the project has a genuine end-to-end prototype.

---

# 51. Key Architectural Decision

The single most important early architecture decision is to **separate pose estimation from exercise interpretation**.

The pose layer answers:

> Where does the system think the body is?

The exercise engine answers:

> What movement does that pattern represent?

The product layer answers:

> What should the participant or clinician be told?

These should remain separate.

Without this separation, changes to the vision model are likely to propagate through every part of the application.

---

# 52. Key Product Decision

The first user-facing product should not be judged by how many movement variables it can display.

It should be judged by whether it reliably supports the loop:

> instruct → observe → recognise → respond → record.

If this loop feels natural and dependable, sophisticated measurements can be added later.

If the loop is unreliable or frustrating, additional analytics will have little commercial value.

---

# 53. Proposed Definition of MVP

For this project, the MVP is defined as:

> **A camera-based application that guides a participant through a short programme of functional exercises, automatically recognises performance for a small set of movements, provides limited real-time feedback, and records a concise session summary suitable for later review.**

The MVP does **not** need to diagnose, prescribe or replace professional supervision.

---

# 54. Immediate Next Actions

The recommended next actions are:

1. select the first pose-estimation technology for experimentation;
2. create the initial repository;
3. build the Pose Sandbox;
4. create the recording/replay pipeline;
5. collect a small Sit-to-Stand development dataset;
6. implement STS-001;
7. establish manual ground-truth annotation;
8. measure repetition-detection accuracy;
9. test frontal versus frontal-oblique camera placement;
10. only then add the second exercise.

The first meaningful technical milestone should be:

> **A recorded Sit-to-Stand sequence is replayed through the system and every genuine repetition is identified correctly, with no false repetitions.**

Once that works consistently across different recordings and users, the project has crossed from concept documentation into a demonstrable technical product.
