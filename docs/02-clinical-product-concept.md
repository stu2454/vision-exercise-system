# 02 — Clinical / Product Concept

**Project:** Vision Exercise System  
**Document:** 02-clinical-product-concept.md  
**Status:** Working draft v0.1

## 1. Purpose

This document defines the clinical and product concept for the Vision Exercise System. It is intended to keep the technical build anchored to a useful rehabilitation workflow without prematurely turning the prototype into a diagnostic or autonomous clinical system.

## 2. Clinical context

Many rehabilitation, falls-prevention and restorative-care programmes rely on repeated functional exercise between professional contacts. Common examples include:

- sit-to-stand practice;
- static and dynamic balance tasks;
- stepping;
- reaching;
- marching;
- lower-limb strengthening;
- task-oriented functional movement.

The effectiveness of these programmes depends partly on adequate dose, progression, adherence and correct performance.

In home delivery, however, professionals often have limited information about what occurs between visits.

## 3. Product concept

The Vision Exercise System is intended to support an already-prescribed home exercise programme by combining:

- clear exercise instruction;
- camera-based observation;
- simple movement recognition;
- limited real-time feedback;
- automatic exercise logging;
- concise review information.

The system should augment professional care rather than replace it.

## 4. What the system should know

The initial system should focus on questions such as:

- Is the participant visible and appropriately positioned?
- Has the exercise started?
- Was a repetition completed?
- How many repetitions were completed?
- How long did the movement take?
- Was the prescribed hold completed?
- Was obvious external support used?
- Was a large movement error repeatedly observed?
- Did the participant stop or leave the capture area?

These questions are operationally useful and are more defensible than attempting early diagnostic inference.

## 5. What the system should not claim initially

The first product should not claim to determine:

- diagnosis;
- falls risk;
- exact muscle strength;
- exact joint kinetics;
- centre of pressure;
- safe independent exercise suitability;
- need for medical review;
- clinical deterioration;
- treatment effectiveness.

Some of these may become research or validation questions later.

## 6. Participant experience

The participant experience should be deliberately simple.

A typical session might be:

```text
START SESSION
    ↓
CAMERA CHECK
    ↓
EXERCISE INSTRUCTION
    ↓
PERFORM EXERCISE
    ↓
SIMPLE FEEDBACK
    ↓
NEXT EXERCISE
    ↓
SESSION COMPLETE
```

The participant should not need to understand pose estimation, confidence scores or biomechanics.

## 7. Professional experience

A professional should receive a concise answer to questions such as:

- Was the programme completed?
- What proportion was completed?
- Were repetitions valid or partial?
- Was support used?
- Were there obvious repeated difficulties?
- Is performance changing over time?

Raw pose streams and technical diagnostics should remain developer-facing unless there is a specific professional need.

## 8. Feedback philosophy

Real-time feedback should be sparse and prioritised.

Suggested hierarchy:

1. safety;
2. task completion;
3. large movement-quality error;
4. pacing;
5. encouragement;
6. optional performance information.

The system should avoid continuous correction.

## 9. Exercise progression

Progression should be configurable and multidimensional.

Potential progression variables include:

- repetitions;
- duration;
- chair height;
- speed;
- reduced hand support;
- narrower base of support;
- larger reach/step target;
- multidirectional tasks;
- dual-task elements;
- reduced cueing.

Automated progression should not be assumed in the first product.

## 10. Measurement hierarchy

The product should distinguish between:

### Level 1 — robust measures

Examples:

- repetition count;
- task completion;
- duration;
- step occurrence;
- hold time;
- obvious support use.

### Level 2 — useful but requiring validation

Examples:

- trunk compensation;
- asymmetry;
- smoothness;
- approximate sway;
- movement velocity.

### Level 3 — advanced/research

Examples:

- kinetic estimates;
- clinical gait measures;
- fall-risk classification;
- diagnostic movement signatures.

This distinction should be preserved in both software and product claims.

## 11. Privacy concept

The preferred production model is local processing.

Where feasible:

```text
camera image
    ↓
on-device pose inference
    ↓
movement events / summary metrics
    ↓
discard frame
```

Raw video should not be retained routinely.

Development recording is a separate explicit activity.

## 12. Commercial hypothesis

Potential value may arise from:

- increased visibility of home exercise adherence;
- reduced need for synchronous observation;
- better-informed programme progression;
- a more engaging exercise experience;
- structured longitudinal records;
- scalable support for restorative or rehabilitation programmes.

These are hypotheses to test rather than assumed benefits.

## 13. Initial product form

Early pilots should favour a known hardware configuration such as:

- a laptop; or
- a tablet with a suitable camera.

This reduces device variability while the movement model is still being established.

## 14. Initial clinical workflow boundary

A professional:

1. determines exercise suitability;
2. configures or selects the programme;
3. participant performs the programme at home;
4. system records supported performance measures;
5. professional reviews summary information;
6. professional decides whether progression, modification or reassessment is needed.

The system assists steps 3–5. It should not autonomously take over steps 1 or 6 in the MVP.

## 15. Product development question

The key early question is not:

> Can computer vision calculate many biomechanical variables?

It is:

> Can the system provide enough reliable information to make home exercise delivery and review meaningfully better?

That question should guide technical priorities.
