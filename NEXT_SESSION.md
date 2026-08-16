# Next session

**Open this first.** Paste the prompt below into Claude Code, then read the
rest if you need reminding where things stand.

Last updated: **16 August 2026**, after Build 6.

---

## Paste this

```text
Read docs/development-log.md, then run python tools/evaluate.py.
We're recording awkward and failed sit-to-stands next.
```

That is enough to orient a cold session. The log carries what was built, the
defects found, and the measurement behind every threshold; the evaluator says
whether it all still holds.

---

## Where things stand

Builds 0–6 of 9 complete. STS-001 sit-to-stand is recognised end to end.

| Measure | Standing |
|---|---|
| Tests | 348 passing |
| Regression dataset | 4 cases, 45 repetitions, **one participant** |
| Count agreement | 95.6% |
| False repetitions | 0 |

The target in Doc 03 §49 is met. It is met on four clean takes by one person in
one room, which is why the next step is what it is.

---

## What we agreed to do next

**Record deliberately awkward and failed attempts**, especially the patterns an
older adult would produce:

- hesitation before committing to the rise
- partial stands — up halfway, then back down
- pushing up off the thighs with the hands
- pausing mid-movement
- sitting down heavily
- using an armrest
- shuffling forward on the seat first

Cases the algorithm handles **badly** are the valuable ones. A dataset of clean
takes cannot tell us where the thresholds are still wrong.

Use `--record-video` on these. Counts have been disputed twice already, and
video makes them decidable by watching rather than by inference.

**Then** Build 7 (participant feedback) — deliberately not before, so feedback
is not built on thresholds that have only ever seen clean movement.

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
