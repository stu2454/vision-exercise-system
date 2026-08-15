# ADR-011 — Pose-stream file format and replay timestamps

**Status:** Accepted
**Date:** 15 August 2026
**Relates to:** ADR-008 (record/replay is core infrastructure), Document 03 §24, §25, §26

---

## Context

Build 3 required a concrete on-disk format for canonical pose streams, and a
concrete rule for what timestamp a replayed video frame carries. Document 03
sketches both but deliberately leaves the details open.

Two specifics had to be settled before recordings could be produced, because
changing either afterwards would invalidate every recording already made.

---

## Decision 1 — JSON Lines rather than a single JSON object

Document 03 §25 sketches:

```json
{"metadata": {...}, "frames": [...]}
```

and notes that a line-oriented format "may be preferable later".

Pose streams are written as JSON Lines now rather than later: one metadata
object on the first line, one frame object per line after it.

### Why

- A recording can be written and read as a stream, without holding a whole
  session in memory. A 10-minute session at 30 fps is 18,000 frames.
- A recording interrupted by a crash or a battery failure stays readable up to
  the last complete line. A truncated single JSON object is unreadable in
  full, which would lose exactly the difficult sessions most worth keeping.
- Appending a frame is a single write with no rewriting of enclosing
  structure.

### Consequences

- The file is not a valid single JSON document; readers must be line-oriented.
  `src/replay/pose_replay.py` is the only reader.
- A truncated final line raises rather than being silently dropped, so a
  damaged recording cannot quietly become a shorter one.

---

## Decision 2 — Replayed video timestamps derive from frame index by default

Video frame timestamps are computed as `frame_index / file_frame_rate`, not
read from the container's presentation time. Media time remains available via
`VideoFileFrameSource(timestamp_source="media")`.

### Why

OpenCV's `CAP_PROP_POS_MSEC` proved unreliable during Build 3: with the
default macOS backend, the third frame of a file repeats the second frame's
timestamp. Non-increasing timestamps are not a cosmetic problem —

- MediaPipe VIDEO mode requires strictly increasing timestamps;
- every velocity feature divides by elapsed time;
- reproducibility across machines is the entire purpose of replay.

Index-derived timestamps are exact for constant-frame-rate files, which is
everything this project records itself, and are identical on every backend and
platform.

### Consequences

- Variable-frame-rate sources, such as a phone recording, are misrepresented
  under the default. `timestamp_source="media"` exists for those, with a
  monotonic guard applied, and the choice should be revisited if VFR
  recordings become a routine part of the regression dataset.
- Live capture is unaffected: the webcam source timestamps frames from a
  monotonic clock at the moment of capture (Document 03 §24).

---

---

## Amendment, 16 August 2026 — the file frame rate must be measured

Decision 2 makes replayed video timestamps depend entirely on the file's
frame rate. That is only safe if the frame rate written into the file is
correct, and initially it was not.

A webcam used for development advertised `CAP_PROP_FPS = 15.0` while actually
delivering 29.4 fps. The claimed figure was written into the pose-stream
metadata and used as the frame rate of the recorded video, so:

- recorded video played at half speed;
- replaying that video produced timestamps twice as far apart as reality,
  putting a silent 2x error into every velocity feature derived from it.

The same camera reported 30.0 fps in a later session, so the claim is not even
consistent between runs on one device.

### Decision

Frame sources measure their own delivered rate (`FrameRateTracker`), and the
measured rate is always preferred over the claimed one. Recordings open only
once a rate has been measured, and store both figures:

```json
{"nominal_fps": 15.0, "measured_fps": 29.4}
```

`nominal_fps` is retained as provenance. Nothing computes with it.

Verified on the camera concerned: recorded container rate now within 0.7% of
truth, and replayed video duration within 0.7% of the live segment it was
recorded from. Trusting the claim would have given 100% error.

### Consequences

- Pose-stream format version becomes 0.2. Readers tolerate a missing
  `measured_fps`, so 0.1 recordings still replay — they simply carry no
  trustworthy rate, and anything computed from their frame rate should be
  treated as suspect.
- A recording started from the first frame is delayed by roughly ten frames
  while the rate is measured.
- Pose streams were never affected: they carry per-frame measured timestamps
  and are self-describing.

---

## Conditions for revisiting

- Pose-stream recordings become large enough that JSON Lines is measurably
  wasteful; a binary or columnar format could then be considered, keeping the
  same logical schema.
- Variable-frame-rate recordings enter the regression dataset, at which point
  the default timestamp source should be reconsidered per recording rather
  than globally.
