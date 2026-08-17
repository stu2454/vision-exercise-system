# Next session

**Open this first.** Paste the prompt below into Claude Code, then read the
rest if you need reminding where things stand.

Last updated: **17 August 2026**, after deploying the browser demo.

---

## Live demo

<https://stu2454.github.io/vision-exercise-system/web/try/>

Participant mode on GitHub Pages, running the real Python engine in the browser
under Pyodide. Nothing leaves the tester's device. Instructions written to be
forwarded as they stand: `docs/for-testers.md`.

**Caveat:** nothing in the test suite verifies that this page executes. Three
faults reached it that 385 tests did not catch. Open it yourself after any
change to `web/`.

## Paste this

```text
Read docs/development-log.md, then run python tools/evaluate.py.
Next is Build 8: single leg stance, timed, eyes open and closed.
```

That is enough to orient a cold session. The log carries what was built, the
defects found, and the measurement behind every threshold; the evaluator says
whether it all still holds.

---

## Where things stand

Builds 0–6 of 9 complete. STS-001 sit-to-stand is recognised end to end.

| Measure | Standing |
|---|---|
| Tests | 385 passing |
| Regression dataset | 6 cases, 73 repetitions, **one participant** |
| Count agreement | 97.3% |
| False repetitions | 0 |
| Failure conditions tested | 6 of ~30 |

The target in Doc 03 §49 is met. It is met on four clean takes by one person in
one room, which is why the next step is what it is.

---

## What we agreed to do next

**Build 8: single leg stance, timed, with and without eyes closed.**

Its purpose in the sequence is architectural, not clinical: can a second
exercise use the same canonical pose, feature, event and storage
infrastructure without special-case rewrites? If it needs the core changed,
the abstraction is not earning its keep.

Four things to settle before writing code:

1. **It is a timed hold, not a repetition count.** The result contract and the
   state model both differ from STS-001. Doc 03 §19 sketches
   `SETUP → TARGET_STANCE → HOLDING → COMPLETED / RECOVERY_STEP / SUPPORT_USED`.
2. **Eyes closed is probably not observable.** MediaPipe Pose carries no eyelid
   detail, and face landmarks at 2–3 m would not support it reliably anyway. It
   likely has to be a protocol instruction recorded as metadata — and if so the
   system must not imply it verified anything.
3. **Sway from a single camera is not centre-of-pressure sway** (CLAUDE.md §37).
   Level 2 at best, and it must be labelled as such.
4. **Recovery steps and reaching for support** are the clinically interesting
   events, and neither is currently detectable.

Still outstanding for STS-001: hand support and armrest use are untested, and
`docs/failure-conditions.md` lists roughly two dozen other untested conditions.

---

## Running a session

```bash
cd ~/dev/vision-exercise-system
source .venv/bin/activate
```

Framing check first. Get `GOOD POSITION` both **seated and standing**, then `q`:

```bash
python -m src.app setup
```

Then the take:

```bash
python -m src.app exercise --camera-view frontal --record --record-video
```

**Before recording:** turn off macOS camera effects — Edge Light, Centre
Stage, Studio Light, background blur. The camera control in the menu bar shows
them while the camera is live. Edge Light changes your illumination whenever
the camera opens, which makes lighting a function of the software rather than
the room. See `docs/failure-conditions.md`.

Physically:

1. Sit down, in shot.
2. Raise **one** arm bent at the elbow, hold ~1 s until the bar fills.
3. Wait out the 3-second countdown, arm down.
4. Do the repetitions. **Count them, and write down what you did.**
5. Raise **both** arms for ~0.6 s to finish.

Afterwards:

```bash
ls -t recordings/ | head -1
python tools/inspect_recording.py recordings/<id>.jsonl
python -m src.app score recordings/<id>.jsonl --expect <count>
```

Then tell Claude the recording ID and exactly what you did, in order.

---

## Quick reference

| Command | Does |
|---|---|
| `python -m src.app check` | Verify camera, model and engine |
| `python -m src.app setup` | Framing check, records nothing |
| `python -m src.app exercise` | Run STS-001 live |
| `python -m src.app score FILE.jsonl` | Score a recording, no inference |
| `python tools/evaluate.py` | Full regression report |
| `python tools/inspect_recording.py FILE.jsonl` | Quality, segments, framing |
| `python tools/benchmark.py --synthetic` | Sustained frame rate |
| `python -m pytest` | 348 tests |

The venv was created with `uv` and has no `pip` — use `uv pip install` if you
need to add anything.

---

## Where the real record lives

| File | Holds |
|---|---|
| `docs/development-log.md` | **The handover.** What was built, every defect, every measurement |
| `CLAUDE.md` | Project rules and architecture constraints |
| `docs/01`–`05` | The source-of-truth project documents |
| `docs/decisions/` | ADRs, including 011 (pose format) and 012 (Raspberry Pi) |
| `test_data/regression/` | Ground truth, one case file per recording |
| `recordings/` | Your pose streams — local, gitignored, never committed |

---

## Keeping this file useful

Update it at the end of a working session, not the start of the next one. Three
things go stale fastest and are worth checking each time:

1. **The paste prompt** — does it still point at the right next thing?
2. **The numbers** — rerun `python tools/evaluate.py` and correct them.
3. **What we agreed to do next** — the reason matters as much as the task, so
   keep the "why" sentence with it.

If a few weeks have passed and this file looks stale, trust
`docs/development-log.md` and `git log --oneline` over it.
