# 04 — Exercise Specifications

**Project:** Vision Exercise System  
**Document:** 04-exercise-specification.md  
**Status:** Draft v0.1  
**Purpose:** Define how individual exercises are represented, delivered, observed, measured and progressed within the Vision Exercise System.

---

## 1. Purpose

The Vision Exercise System requires a consistent way of translating an exercise from a clinical or rehabilitation concept into something that can be:

- explained clearly to a participant;
- observed through a commodity RGB camera;
- segmented into meaningful movement phases;
- assessed sufficiently well to determine whether the exercise was completed;
- monitored for obvious movement errors or safety concerns;
- progressed or regressed according to participant performance; and
- recorded in a form that can support review by a clinician, allied health professional or other authorised user.

This document defines that exercise specification framework.

The initial objective is **not** to reproduce laboratory biomechanics or make diagnostic claims. The system should first become good at a smaller number of useful things:

1. recognise the exercise being performed;
2. determine whether a repetition or task has been completed;
3. measure a small number of robust and interpretable performance variables;
4. identify large or clinically meaningful deviations where this can be done reliably;
5. provide simple, timely feedback; and
6. produce a concise record of performance over time.

The specification therefore deliberately separates:

- **clinical intent** — why the exercise is being prescribed;
- **participant experience** — what the participant sees and hears;
- **movement model** — how the exercise is represented internally;
- **pose-derived measures** — what can be estimated from camera data;
- **decision logic** — how repetitions, errors and progress are determined; and
- **validation status** — how much confidence should be placed in each metric.

---

## 2. Design principles

### 2.1 Clinical usefulness before biomechanical sophistication

A technically impressive measure is of little value if it cannot inform exercise delivery, progression, adherence or review.

Measures should therefore be included only when they answer a useful question, such as:

- Did the person complete the exercise?
- How many repetitions were completed?
- Did performance improve?
- Was the movement slower, less controlled or more asymmetric than usual?
- Did the participant require repeated instruction?
- Was an obvious unsafe event detected?

---

### 2.2 Prefer robust measures over fragile precision

The system will operate in ordinary homes rather than controlled laboratories.

Expected sources of variability include:

- camera height and angle;
- different room layouts;
- variable lighting;
- occlusion by furniture or clothing;
- different body sizes;
- walking aids;
- imperfect visibility of the feet;
- intermittent pose-estimation errors; and
- participants moving outside the ideal capture volume.

Where a simple categorical measure is likely to be dependable but a precise numerical measure is not, the simpler measure should be preferred.

For example:

> “Rep completed with adequate extension”

may initially be more defensible than:

> “Peak knee extension was 176.4°”.

---

### 2.3 Separate measurement from interpretation

The system should retain observable data separately from higher-level judgements.

For example:

- **Observed:** trunk angle increased by approximately 18° during rising.
- **Derived:** forward trunk flexion increased relative to prior repetitions.
- **Interpretation:** possible compensatory strategy.
- **Clinical judgement:** should remain with an appropriately qualified person unless the inference has been validated and approved for automated use.

---

### 2.4 Exercise specifications should be implementation-independent

The exercise model should not be tightly coupled to a particular pose-estimation library, camera or machine-learning model.

An exercise specification should describe concepts such as:

- hip vertical displacement;
- knee flexion;
- trunk inclination;
- foot displacement;
- base of support;

rather than implementation-specific variables such as a particular model's landmark index.

A separate technical mapping layer should translate the canonical exercise model into the landmarks available from the chosen pose-estimation technology.

---

### 2.5 Real-time feedback should be sparse

Older participants and people undertaking rehabilitation can be disadvantaged by excessive instruction.

Feedback should therefore:

- address one issue at a time;
- favour positive reinforcement;
- avoid repeated correction of minor deviations;
- distinguish between movement quality and safety;
- stop or modify the exercise when necessary; and
- be configurable by the treating professional.

---

### 2.6 Progression should be explicit

Every exercise should define how it can become:

- easier;
- harder;
- more stable;
- less supported;
- faster or slower;
- more cognitively demanding;
- more functionally relevant; or
- more variable.

Progression should not depend solely on increasing repetition count.

---

## 3. Measurement confidence levels

Each metric in the exercise library should be assigned an intended confidence level.

### Level 1 — Product-ready / robust

Metrics expected to be sufficiently robust for early product use with commodity RGB cameras.

Examples:

- exercise started/completed;
- repetition count;
- broad movement phase;
- movement duration;
- gross body displacement;
- step occurrence;
- approximate stance width;
- whether hands appear to be used for support;
- whether the participant leaves the capture area.

Level 1 measures should form the core of the first usable system.

---

### Level 2 — Useful but requires validation

Measures that are plausible and potentially clinically useful but require comparison against reference measures and testing across users and environments.

Examples:

- movement asymmetry;
- trunk compensation;
- sit-to-stand velocity;
- step timing;
- movement smoothness;
- approximate sway;
- range-of-motion estimates;
- repeated change in movement strategy.

These measures may be exposed initially as exploratory or clinician-facing metrics rather than definitive judgements.

---

### Level 3 — Advanced / research

Measures that risk implying biomechanical or clinical precision beyond what a single commodity RGB camera can reliably provide without substantial validation.

Examples:

- joint moments;
- ground reaction forces;
- centre-of-pressure estimates;
- clinically diagnostic gait parameters;
- precise postural sway metrics;
- fall-risk classification derived from unvalidated movement markers.

Level 3 functionality should remain outside the initial commercial product unless evidence and regulatory strategy justify its inclusion.

---

# 4. Common Exercise Specification

Every exercise should be represented using the following structure.

## 4.1 Identification

| Field | Description |
|---|---|
| Exercise ID | Stable machine-readable identifier |
| Exercise name | Participant-facing name |
| Exercise family | Strength, balance, stepping, mobility, functional, dual-task etc. |
| Version | Specification version |
| Status | Draft, pilot, validated, deprecated |
| Difficulty | Nominal difficulty level |
| Equipment | Chair, bench, rail, none etc. |

---

## 4.2 Clinical intent

Each exercise should state:

- primary functional objective;
- secondary objectives;
- principal physical capacities targeted;
- likely use cases;
- major contraindications or precautions; and
- whether professional supervision is recommended.

The application should not infer suitability solely from these descriptions. Exercise prescription remains a separate function.

---

## 4.3 Participant setup

The specification should define:

- participant orientation relative to camera;
- preferred camera distance;
- required visible body regions;
- required environmental objects;
- acceptable footwear;
- whether a mobility aid may be used;
- whether a chair or support surface must be fixed;
- minimum clear floor area; and
- any camera calibration required.

The system should confirm adequate setup before commencing.

---

## 4.4 Participant instruction

Each exercise should have three instruction layers.

### Short instruction

One sentence displayed immediately before the exercise.

### Detailed instruction

Optional explanation available before starting or on request.

### In-exercise cues

Short prompts that can be triggered during performance.

Example:

> Stand up tall, then sit back down with control.

Possible cues:

- “Stand tall.”
- “Sit back slowly.”
- “Try not to use your hands.”
- “Good — keep going.”

---

## 4.5 Required observable landmarks

The specification should identify the body regions necessary for reliable execution.

Typical groups include:

- head;
- shoulders;
- trunk;
- pelvis/hips;
- knees;
- ankles;
- feet;
- hands/wrists.

A movement should not be scored when essential landmarks are unavailable for a sustained period.

---

## 4.6 Derived features

Canonical derived features may include:

- joint angle estimates;
- vertical displacement;
- horizontal displacement;
- segment inclination;
- relative landmark distance;
- foot separation;
- movement velocity;
- movement duration;
- symmetry index;
- stability of support;
- hand contact;
- body orientation; and
- movement variability.

These should be calculated from filtered pose data rather than raw frame-by-frame landmarks.

---

## 4.7 Exercise state machine

Where possible, exercises should be represented as a finite state machine.

Example:

```text
READY
  ↓
INITIATING
  ↓
MOVING
  ↓
TARGET_POSITION
  ↓
RETURNING
  ↓
COMPLETED
```

State transitions should normally depend on a combination of:

- landmark position;
- movement direction;
- threshold crossing;
- dwell time; and
- temporal consistency.

A single noisy frame should never be sufficient to trigger a state transition.

---

## 4.8 Repetition validity

A repetition may be classified as:

- **valid** — completed within required movement criteria;
- **partial** — recognisable attempt but target position not reached;
- **invalid** — movement does not meet the exercise definition;
- **aborted** — participant begins but stops;
- **unscorable** — insufficient pose confidence or occlusion.

The system should distinguish these categories rather than treating every movement as either a success or failure.

---

## 4.9 Movement quality

Movement quality variables should be expressed separately from repetition validity.

A participant might therefore complete:

> 8 valid repetitions, of which 3 showed increased trunk compensation.

This is preferable to rejecting otherwise useful repetitions because movement was imperfect.

---

## 4.10 Safety events

Exercise specifications should identify detectable events that may require interruption.

Examples include:

- sudden loss of vertical stability;
- unexpected rapid downward movement;
- participant leaving the expected support region;
- unplanned contact with nearby furniture;
- repeated inability to complete a movement;
- prolonged non-response;
- participant verbally requesting stop.

Computer vision should not be presented as a substitute for clinical supervision or emergency monitoring.

---

## 4.11 Feedback hierarchy

Feedback should be prioritised as:

1. **Safety**
2. **Task completion**
3. **Large movement-quality error**
4. **Pacing**
5. **Encouragement**
6. **Optional performance information**

Only the highest-priority relevant cue should normally be delivered at any one time.

---

## 4.12 Exercise progression

Possible progression dimensions include:

- repetitions;
- duration;
- movement amplitude;
- speed;
- reduced upper-limb support;
- narrower base of support;
- altered stance;
- increased target distance;
- multidirectional movement;
- cognitive dual task;
- visual challenge;
- reduced external cueing.

Progression rules should be configurable rather than fully automated in the initial system.

---

# 5. Exercise 001 — Sit-to-Stand

## 5.1 Identification

| Field | Value |
|---|---|
| Exercise ID | STS-001 |
| Name | Sit-to-Stand |
| Family | Functional lower-limb strength |
| Equipment | Stable chair |
| Initial confidence level | Level 1 core + Level 2 exploratory metrics |
| Preferred view | Approximately frontal-oblique |
| Repetitive | Yes |

---

## 5.2 Clinical intent

Sit-to-stand is a functional task requiring coordinated lower-limb force generation, trunk control and balance.

Potential objectives include:

- improving functional lower-limb strength;
- improving transfer ability;
- increasing repeated movement capacity;
- improving control during rising and sitting;
- reducing reliance on upper limbs; and
- providing a functional exercise that is easily understood.

---

## 5.3 Setup

The participant should:

- sit on a stable chair;
- position the chair so that the body is clearly visible;
- place feet comfortably on the floor;
- avoid chairs with wheels;
- have sufficient space in front of the chair;
- place a stable support nearby if prescribed.

Preferred camera view should permit observation of:

- shoulders;
- hips;
- knees;
- ankles;
- feet where possible; and
- hands.

A frontal-oblique view may provide a useful compromise between observing symmetry and estimating flexion/extension.

---

## 5.4 Participant instruction

### Short instruction

> Stand all the way up, then sit back down with control.

### Optional detailed instruction

> Sit near the front of the chair with your feet comfortably underneath you. Lean forward as needed, stand until you are upright, then slowly lower yourself back onto the chair. Use your hands only if you have been asked to.

---

## 5.5 Core states

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

### SEATED

Indicative characteristics:

- pelvis at low vertical position;
- hips behind or close to knees in image-space relationship;
- little vertical motion;
- trunk relatively stable.

### FORWARD_PREPARATION

Possible characteristics:

- trunk moves forwards;
- shoulder position shifts relative to hips;
- hip height changes little initially.

This phase is useful for analysis but does not need to be explicitly detected in V0.1.

### RISING

Characteristics:

- pelvis/hip landmarks move upward;
- knee angle increases;
- trunk begins returning towards upright;
- movement continues consistently for a minimum number of frames.

### STANDING

Characteristics:

- hip height reaches participant-specific upper range;
- knee extension reaches participant-specific standing range;
- trunk is approximately upright;
- vertical movement stabilises.

### DESCENDING

Characteristics:

- hip position moves downwards;
- knee flexion increases;
- pelvis returns towards the chair.

### SEATED COMPLETION

Characteristics:

- pelvis returns to participant-specific seated range;
- downward movement ceases;
- brief stable seated state is detected.

---

## 5.6 V0.1 repetition detection

A complete repetition should require:

1. stable seated state;
2. sustained upward pelvis movement;
3. attainment of a standing threshold;
4. sustained downward pelvis movement;
5. return to seated threshold.

The thresholds should be calibrated to the individual at the beginning of the exercise rather than relying on fixed pixel distances.

An early implementation might define:

```text
seated_height = rolling median hip height during setup
standing_height = rolling median hip height during first confirmed stand

normalised_height =
    (current_hip_height - seated_height)
    / (standing_height - seated_height)
```

Approximate state thresholds could then operate on normalised movement.

Exact numerical thresholds should be established experimentally rather than embedded prematurely in the clinical specification.

---

## 5.7 Core V0.1 metrics

### Repetition count

Number of valid completed sit-to-stand cycles.

**Confidence:** Level 1.

### Repetition duration

Time from initiation of rising to return to seated state.

**Confidence:** Level 1.

### Rise time

Approximate time from rise initiation to stable standing.

**Confidence:** Level 1–2.

### Descent time

Approximate time from descent initiation to seated position.

**Confidence:** Level 1–2.

### Completion ratio

```text
valid repetitions / attempted repetitions
```

**Confidence:** Level 1.

### Upper-limb assistance

Categorical estimate:

- no visible hand support;
- possible hand support;
- clear hand support;
- unscorable.

Potential evidence includes hand proximity/contact with:

- chair arms;
- thighs;
- nearby support surface.

**Confidence:** Level 1–2 depending on camera view.

---

## 5.8 Exploratory Level 2 metrics

### Trunk strategy

Estimate peak forward trunk inclination during rising.

Possible uses:

- monitor change over repetitions;
- compare relative movement within the same participant;
- identify unusually large compensation.

This should initially be treated as a within-person trend rather than a normative biomechanical measurement.

### Left-right loading proxy

Potentially inferred from:

- asymmetric hip movement;
- unequal knee trajectories;
- trunk lateral displacement.

A single-camera system cannot directly measure force distribution. Any asymmetry score should therefore be clearly described as a **movement asymmetry proxy**, not weight-bearing asymmetry.

### Movement velocity

Pelvis vertical velocity may provide a useful functional performance marker.

Possible metrics:

- peak normalised vertical velocity;
- average rise velocity.

These require validation before being used as clinical outcomes.

### Movement consistency

Variation across repetitions in:

- rise time;
- descent time;
- peak trunk inclination;
- normalised range.

This may be useful for identifying fatigue or inconsistent performance.

---

## 5.9 Movement-quality observations

Potential movement observations include:

| Observation | Detection concept | Initial status |
|---|---|---|
| Incomplete standing | standing threshold not reached | Level 1 |
| Incomplete sitting | seated threshold not reached | Level 1 |
| Very rapid descent | high downward velocity | Level 1–2 |
| Hand assistance | hand contact/proximity | Level 1–2 |
| Excess trunk flexion | trunk angle relative to personal range | Level 2 |
| Lateral trunk shift | shoulder/pelvis lateral translation | Level 2 |
| Movement asymmetry | left/right trajectory difference | Level 2 |
| Pause during rise | velocity approaches zero before standing | Level 1–2 |

---

## 5.10 Feedback examples

### Task feedback

- “Stand all the way up.”
- “Come back to sitting.”
- “Good — that’s one.”

### Pacing feedback

- “Try to sit down a little more slowly.”
- “Take your time.”

### Movement-quality feedback

Only if enabled:

- “Try to keep your weight centred.”
- “Try not to push with your hands.”

### Safety feedback

- “Stop and steady yourself.”
- “Hold the support.”
- “Please sit down.”

Safety feedback should terminate or pause the current exercise where appropriate.

---

## 5.11 Progressions

Possible progressions include:

1. increased repetition count;
2. increased set duration;
3. reduced chair height;
4. arms folded across chest;
5. slower controlled descent;
6. faster concentric phase where appropriate;
7. addition of a reach after standing;
8. sit-to-stand followed by step;
9. dual-task sit-to-stand;
10. reduced external support.

Not all progressions are suitable for all participants.

---

## 5.12 Regressions

Possible regressions include:

- higher chair;
- use of armrests;
- use of hands on thighs;
- external stable support;
- fewer repetitions;
- longer rest between repetitions;
- partial sit-to-stand;
- clinician or carer supervision.

---

# 6. Exercise 002 — Static Standing Balance

## 6.1 Identification

| Field | Value |
|---|---|
| Exercise ID | BAL-001 |
| Name | Static Standing Balance |
| Family | Balance |
| Equipment | Optional stable support |
| Preferred view | Frontal |
| Repetitive | No |
| Primary task type | Timed hold |

---

## 6.2 Clinical intent

Potential objectives include:

- maintaining upright standing;
- reducing reliance on upper-limb support;
- altering base of support;
- increasing postural control challenge;
- building confidence in standing tasks.

---

## 6.3 Variants

The exercise family may include:

- comfortable stance;
- feet together;
- semi-tandem;
- tandem;
- single-leg stance where appropriate.

Each variant should be encoded as a parameter rather than necessarily being a separate exercise.

---

## 6.4 Core V0.1 metrics

- hold duration;
- target stance attained;
- loss of target stance;
- obvious step response;
- hand support detected;
- exercise aborted;
- participant moved outside capture area.

These are more defensible early metrics than attempting clinical posturography from a single RGB camera.

---

## 6.5 Exploratory metrics

Possible Level 2 measures include:

- trunk displacement;
- shoulder displacement;
- pelvis displacement;
- approximate movement envelope;
- frequency of corrective movements.

The system should avoid describing these as centre-of-pressure sway.

---

## 6.6 State model

```text
SETUP
  ↓
TARGET_STANCE
  ↓
HOLDING
  ↓
RECOVERY_STEP / SUPPORT_USED / COMPLETED
```

---

## 6.7 Feedback

Examples:

- “Bring your feet a little closer.”
- “Hold that position.”
- “Use the support if you need it.”
- “Good — keep looking ahead.”

---

# 7. Exercise 003 — Weight Shifting

## 7.1 Identification

| Field | Value |
|---|---|
| Exercise ID | BAL-002 |
| Name | Side-to-Side Weight Shift |
| Family | Dynamic balance |
| Preferred view | Frontal |
| Equipment | Optional support |

---

## 7.2 Clinical intent

This exercise develops controlled movement of the body within the base of support.

Possible objectives:

- lateral control;
- preparation for stepping;
- controlled transfer of body mass;
- balance confidence;
- movement symmetry.

---

## 7.3 Movement model

```text
CENTRE
  ↓
SHIFT_LEFT
  ↓
LEFT_TARGET
  ↓
RETURN_CENTRE
  ↓
SHIFT_RIGHT
  ↓
RIGHT_TARGET
  ↓
RETURN_CENTRE
```

---

## 7.4 Core metrics

- number of completed shifts;
- left target attained;
- right target attained;
- movement duration;
- movement amplitude relative to personal calibrated range;
- unintended step;
- support use.

---

## 7.5 Exploratory metrics

- left-right amplitude difference;
- left-right timing difference;
- trunk versus pelvis contribution;
- smoothness;
- change over repeated cycles.

Again, the system should avoid claiming direct measurement of weight distribution.

---

# 8. Exercise 004 — Stepping

## 8.1 Identification

| Field | Value |
|---|---|
| Exercise ID | STEP-001 |
| Name | Target Step |
| Family | Dynamic balance / stepping |
| Preferred view | Frontal-oblique |
| Equipment | Optional support |

---

## 8.2 Clinical intent

Potential objectives include:

- improving initiation of stepping;
- increasing step size;
- practising controlled return;
- multidirectional balance;
- improving ability to respond to environmental demands.

---

## 8.3 Variants

Direction may be parameterised as:

- forward;
- backward;
- lateral left;
- lateral right;
- diagonal;
- alternating;
- externally cued/randomised.

---

## 8.4 State model

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

## 8.5 V0.1 metrics

- step detected;
- correct leg used;
- correct direction;
- approximate step magnitude;
- foot returned;
- completion time;
- number of completed steps;
- loss of balance requiring an additional recovery step.

---

## 8.6 Exploratory metrics

- step initiation time;
- left-right differences;
- foot clearance proxy;
- trajectory smoothness;
- stance recovery time.

Foot clearance should be treated cautiously because depth and camera perspective can substantially affect estimates.

---

## 8.7 Target-based interaction

The stepping exercise provides an opportunity for game-like interaction.

Targets may be rendered visually on screen while the system estimates whether the appropriate foot has reached the corresponding virtual zone.

This extends the logic originally used in stepping-based exergames while removing the requirement for a physical instrumented mat.

Target design may vary:

- fixed;
- sequential;
- random;
- colour-coded;
- direction-only;
- speed-adjusted;
- dual-task.

---

# 9. Exercise 005 — Functional Reach

## 9.1 Identification

| Field | Value |
|---|---|
| Exercise ID | REACH-001 |
| Name | Standing Reach |
| Family | Functional balance |
| Preferred view | Depends on target direction |
| Equipment | Optional support |

---

## 9.2 Clinical intent

Potential objectives include:

- controlled movement towards the limits of stability;
- trunk and upper-limb coordination;
- functional reaching;
- balance confidence;
- return to stable upright stance.

---

## 9.3 Variants

Targets can be:

- forward;
- lateral;
- diagonal;
- high;
- low;
- alternating;
- random.

---

## 9.4 Core metrics

- target reached;
- correct hand;
- response time;
- movement time;
- return to starting posture;
- step used;
- support used.

---

## 9.5 Exploratory metrics

- reach amplitude;
- trunk contribution;
- pelvic displacement;
- asymmetry;
- movement smoothness.

The system should not initially represent camera-derived reach distance as equivalent to a clinical Functional Reach Test unless specifically validated for that purpose.

---

# 10. Exercise 006 — Marching in Place

## 10.1 Identification

| Field | Value |
|---|---|
| Exercise ID | STEP-002 |
| Name | Marching in Place |
| Family | Dynamic balance / mobility |
| Preferred view | Frontal |
| Equipment | Optional support |

---

## 10.2 Clinical intent

Potential objectives include:

- repeated weight transfer;
- foot clearance;
- alternating lower-limb movement;
- dynamic balance;
- endurance;
- stepping rhythm.

---

## 10.3 State model

Each leg alternates through:

```text
STANCE
  ↓
LIFT
  ↓
PEAK
  ↓
LOWER
  ↓
STANCE
```

---

## 10.4 V0.1 metrics

- alternating steps counted;
- exercise duration;
- cadence;
- interruption frequency;
- correct alternation;
- support use.

---

## 10.5 Exploratory metrics

- left-right timing difference;
- relative knee-lift height;
- variation in cadence;
- movement amplitude decline over time;
- upper-body compensation.

---

# 11. Parameterisation

Exercises should be defined using adjustable parameters wherever possible.

Example:

```yaml
exercise_id: STS-001
target_repetitions: 8
sets: 2
rest_seconds: 60
upper_limb_support: permitted
tempo:
  rise: self_selected
  descent: controlled
feedback:
  repetition_count: true
  movement_quality: true
  encouragement: moderate
```

This allows the same underlying exercise to support different prescriptions without creating many separate versions.

---

# 12. Exercise session output

Each completed exercise should generate a structured result.

Example:

```json
{
  "exercise_id": "STS-001",
  "exercise_version": "0.1",
  "prescribed_repetitions": 10,
  "attempted_repetitions": 10,
  "valid_repetitions": 9,
  "partial_repetitions": 1,
  "mean_rep_duration_seconds": 4.8,
  "mean_rise_time_seconds": 1.9,
  "mean_descent_time_seconds": 2.3,
  "hand_support": {
    "none": 7,
    "possible": 1,
    "clear": 2
  },
  "quality_flags": {
    "rapid_descent": 1,
    "large_trunk_compensation": 2
  },
  "safety_events": [],
  "pose_quality": "adequate"
}
```

Exact data fields should be finalised alongside the data architecture.

---

# 13. Calibration

Calibration should be kept as simple as possible.

Depending on exercise, useful calibration may include:

- relaxed standing pose;
- seated pose;
- comfortable stance width;
- one practice repetition;
- one practice step.

Calibration should establish participant-specific reference ranges rather than normative ideals.

Potential calibration outputs include:

```text
standing_hip_height
seated_hip_height
standing_knee_angle
comfortable_stance_width
left_step_reference
right_step_reference
```

These values should be treated as session or participant reference measures, not precise anatomical measurements.

---

# 14. Pose confidence and missing data

No exercise logic should assume that pose estimates are continuously correct.

The system should monitor:

- landmark confidence;
- number of missing landmarks;
- sudden implausible jumps;
- prolonged occlusion;
- body leaving the frame.

Possible statuses:

```text
GOOD
DEGRADED
INSUFFICIENT
```

When pose quality becomes insufficient:

1. scoring should pause;
2. the participant should receive a simple repositioning prompt;
3. incomplete movements should not be counted against performance;
4. the system should resume only after pose quality stabilises.

---

# 15. Personal baselines

A major advantage of repeated home use is the ability to compare the participant with themselves rather than a population norm.

Potential longitudinal variables include:

- repetitions completed;
- average repetition time;
- variability;
- support use;
- exercise difficulty;
- target amplitude;
- interruptions;
- adherence.

This may ultimately be more useful for remote rehabilitation than attempting to infer a clinical diagnosis from isolated camera metrics.

---

# 16. Exercise difficulty model

Difficulty should be multidimensional.

A future exercise object might represent:

```yaml
difficulty:
  strength: 2
  balance: 1
  coordination: 1
  cognitive: 0
  endurance: 2
```

This provides a better basis for progression than a single global difficulty number.

---

# 17. Clinician configuration

An authorised clinician or exercise professional should eventually be able to configure:

- exercise selection;
- number of repetitions;
- sets;
- duration;
- support permitted;
- progression;
- target amplitude;
- feedback frequency;
- feedback type;
- whether movement-quality cues are enabled;
- stop rules.

Defaults should minimise configuration burden.

---

# 18. Participant-facing design

The exercise experience should be deliberately simple.

The primary display may include:

- exercise name;
- short instruction;
- demonstration animation/video;
- repetition or time target;
- large progress indicator;
- minimal pose/avatar representation if useful;
- one feedback message at a time.

The system should avoid presenting raw joint angles, confidence scores or complex biomechanical information to participants.

---

# 19. Initial V0.1 Exercise Set

A realistic first implementation should be deliberately constrained.

Recommended V0.1 exercises:

| Exercise | Primary capability tested |
|---|---|
| Sit-to-Stand | phase detection and repetition counting |
| Static Balance | timed state and support detection |
| Side-to-Side Weight Shift | controlled displacement |
| Forward/Lateral Step | foot movement and target interaction |
| Standing Reach | upper-body target interaction |
| Marching in Place | alternating movement and cadence |

Together these exercises test most of the capabilities required for a broader exercise library without attempting full gait analysis.

---

# 20. Validation strategy

Each exercise should pass through progressive validation stages.

## Stage 1 — Technical feasibility

Questions:

- Can the pose model see the required landmarks?
- Can the movement states be separated?
- Can repetitions be detected reliably?
- What camera positions fail?

Small convenience samples are sufficient.

---

## Stage 2 — Algorithm reliability

Compare automated outputs against human-observed ground truth.

Potential measures:

- repetition count agreement;
- phase timing;
- false positive rate;
- false negative rate;
- agreement for categorical movement-quality flags.

---

## Stage 3 — Ecological robustness

Test across:

- different homes;
- camera devices;
- lighting conditions;
- clothing;
- furniture;
- participant body sizes;
- mobility aids where relevant.

This stage is particularly important because real-world failure modes are unlikely to resemble controlled laboratory conditions.

---

## Stage 4 — Clinical usefulness

Only after technical reliability is established should the project ask whether Level 2 variables meaningfully support:

- clinical decision-making;
- progression;
- remote review;
- identification of deterioration;
- participant engagement.

---

## Stage 5 — Clinical validation where required

Any feature presented as:

- a clinical assessment;
- a predictor of falls;
- a diagnostic measure;
- a treatment recommendation; or
- a validated clinical outcome

will require a substantially stronger evidence base and potentially a different regulatory treatment.

This should not be assumed to be necessary for the first commercial product.

---

# 21. Open Technical Questions

The following issues should be tested rather than decided conceptually.

### Camera position

Is a frontal view sufficient for the initial exercise set, or is a frontal-oblique setup materially better?

### Feet

How reliably can common pose models localise feet when:

- trousers obscure the ankle;
- the chair occludes part of the lower leg;
- the participant stands close to furniture?

### Hand support

Can hand contact with chair arms, thighs or rails be detected robustly enough to provide useful categorical feedback?

### Occlusion

How should the system handle short periods in which one side of the body disappears?

### Exercise calibration

Can the system infer seated and standing thresholds automatically during the first repetition, or should a brief explicit calibration be used?

### Multi-person detection

What should happen if a carer walks into frame?

### Mobility aids

Which exercises should support:

- walking sticks;
- four-wheeled walkers;
- rails;
- chair arms?

Support for mobility aids should be explicit rather than accidental.

---

# 22. Product Boundary

The initial system should be framed principally as an **exercise delivery, monitoring and remote review platform**.

It should avoid prematurely positioning itself as:

- a fall-risk diagnostic system;
- a biomechanical laboratory;
- a substitute for clinical assessment;
- an autonomous rehabilitation prescriber.

A credible commercial pathway is more likely to emerge from doing a smaller set of useful tasks reliably than from attempting to infer every clinically interesting variable from the camera.

---

# 23. Next Steps

The immediate development tasks arising from this specification are:

1. select the initial pose-estimation stack;
2. define the canonical landmark abstraction layer;
3. build a simple pose recorder and replay utility;
4. capture sample sit-to-stand recordings;
5. implement the STS-001 state machine;
6. compare automated repetition counts against manual annotation;
7. test alternative camera positions;
8. establish the first session-output schema;
9. implement STEP-001 as the second movement model;
10. refine thresholds empirically rather than by assumption.

The sit-to-stand exercise should be treated as the first reference implementation. If the architecture works cleanly for STS-001, its state, measurement, confidence and feedback framework can then be generalised across the remainder of the exercise library.
