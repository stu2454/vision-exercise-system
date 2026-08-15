# 01 — Project Vision

**Project:** Vision Exercise System  
**Document:** 01-project-vision.md  
**Status:** Working draft v0.1

## 1. Vision

Create a practical, camera-based exercise system that can deliver and monitor functional exercise in the home using ordinary RGB cameras and modern computer vision, without requiring an instrumented mat, wearable sensors or proprietary depth-camera hardware.

The long-term opportunity is a system that supports rehabilitation, restorative care, falls-prevention exercise and related home-based programmes while remaining sufficiently simple for older adults to use and sufficiently useful for professionals to review remotely.

## 2. Origin of the idea

The concept builds on earlier work in stepping-based exergaming, falls-prevention exercise and camera-based rehabilitation systems. Earlier generations depended on specialist hardware such as instrumented stepping mats and Microsoft Kinect. Modern monocular pose-estimation models create an opportunity to revisit the concept using commodity cameras and software-defined movement interpretation.

A central lesson from the earlier technology generation is that the product should not depend on a single proprietary sensing platform.

## 3. Problem

Home exercise programmes often suffer from limited supervision between clinical contacts. A professional may prescribe useful exercises but have little objective information about:

- whether the programme was completed;
- how much was completed;
- whether performance changed;
- whether support was used;
- whether the person struggled with particular movements;
- whether the exercise needs review or progression.

Video consultations can help, but they are labour intensive and do not provide continuous asynchronous support.

## 4. Opportunity

A camera-based system could provide a middle layer between unsupervised paper/video exercise programmes and synchronous clinician-delivered telerehabilitation.

The intended interaction is:

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

The system would guide an exercise, recognise gross movement performance, provide limited real-time feedback and retain a concise record for later review.

## 5. Product principles

The system should be:

- **hardware-light** — use commodity cameras where practical;
- **local-first** — process video on-device where possible;
- **clinically conservative** — distinguish observed movement from clinical interpretation;
- **modular** — keep pose estimation replaceable;
- **accessible** — design for older adults from the outset;
- **measurable** — favour useful, repeatable measures over pseudo-biomechanical precision;
- **testable** — develop against recorded, annotated movement data;
- **commercially pragmatic** — solve a useful workflow before attempting a complete digital-health platform.

## 6. Initial product boundary

The initial product is best conceived as:

> **An exercise delivery, adherence monitoring and movement-performance tracking system.**

It is not initially intended to be:

- a diagnostic system;
- a fall-risk predictor;
- an autonomous prescriber;
- a gait laboratory;
- a substitute for professional assessment;
- an emergency monitoring service.

## 7. Initial users

### Primary user

An older adult or rehabilitation participant undertaking an already-prescribed exercise programme at home.

### Secondary user

A physiotherapist, exercise physiologist, allied health professional or appropriately supervised assistant who needs concise information about completion and performance.

## 8. Initial exercise focus

The first exercise families are:

- Sit-to-Stand;
- Static Standing Balance;
- Side-to-Side Weight Shift;
- Forward/Lateral Target Step;
- Standing Reach;
- Marching in Place.

Sit-to-Stand is the first reference implementation.

## 9. Strategic hypothesis

The project will test whether a small number of well-supported exercises measured reliably is more valuable than a large exercise library with weak measurement.

A credible commercial system is likely to emerge from dependable workflow support rather than from maximising the number of derived biomechanical variables.

## 10. Long-term possibilities

If the core interaction proves useful, later development may include:

- remote clinician review;
- longitudinal trend displays;
- programme configuration;
- interactive stepping/reaching targets;
- provider deployment;
- tablet or edge-device packaging;
- cloud synchronisation;
- validated movement-quality measures;
- integration with broader restorative-care or telerehabilitation workflows.

These remain possibilities rather than current commitments.

## 11. Current project objective

The immediate objective is to build a reproducible Pose Sandbox and then a Sit-to-Stand reference implementation that can:

1. observe a participant;
2. represent pose in a vendor-neutral format;
3. recognise movement states;
4. count repetitions;
5. record timing;
6. generate events;
7. save a structured session result;
8. replay the same movement for regression testing.

The project should progress only when each layer is sufficiently stable to justify the next.
