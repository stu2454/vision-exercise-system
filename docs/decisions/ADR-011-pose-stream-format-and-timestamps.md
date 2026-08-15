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

## Conditions for revisiting

- Pose-stream recordings become large enough that JSON Lines is measurably
  wasteful; a binary or columnar format could then be considered, keeping the
  same logical schema.
- Variable-frame-rate recordings enter the regression dataset, at which point
  the default timestamp source should be reconsidered per recording rather
  than globally.
