# STS-001 regression dataset

Ground truth, kept separate from anything the algorithm produces
(Document 03 §27). Nothing in `src/` writes to these files.

## Case files

One YAML file per recording:

```yaml
case_id: sts_gesture_001
recording: dev_20260816_134314.jsonl
true_repetitions: 11        # human-observed, the authority
partial_repetitions: 0
camera_view: frontal
hand_support_reps: []
use_gestures: true          # scored the same way the live session was
notes: >
  What makes this case worth keeping.
```

## Recordings are not committed

Case files reference a pose stream by name. The evaluator searches
`test_data/pose/` then `recordings/`, and **skips** cases whose recording is
absent rather than failing.

Pose streams contain no images, but they still describe a real person's
movement. Whether to commit them is a deliberate decision, not a default
(CLAUDE.md §28, §30). To share a case, copy its recording into
`test_data/pose/`.

## Running

```bash
python tools/evaluate.py            # full report
python tools/evaluate.py --json     # machine-readable
python tools/evaluate.py --case sts_gesture_001
```

Exits non-zero on any false repetition. A conservative miss does not fail the
run: detecting a repetition the participant did not perform is the worse
error (Document 03 §49).

`pytest tests/regression/` asserts the same thing as part of the suite.

## On recalled counts

`sts_frontal_001` records 12 repetitions where the participant remembered 10.
Hip height showed 12 cycles at metronomic 3.1–3.3 s spacing, knee angle
independently corroborated 11 of them, and all 12 reached the same standing
height to within a standard deviation of 0.0046.

Recalled counts are not ground truth. Where a case disagrees with memory, the
evidence for the number belongs in `notes`.

## What this dataset still lacks

Deliberate variation is the point of a regression set (Document 03 §28), and
this one has almost none yet. Missing: slow and fast repetitions, pauses
mid-movement, partial stands, hand support, chair variation, occlusion, poor
lighting, a participant partly out of frame, and more than one person.

Until those exist, a passing run says the algorithm has not regressed on three
clean takes by one person. It does not say the algorithm is good.
