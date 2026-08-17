# Failure conditions to test deliberately

The working list. Document 05 §39 sets out the conditions the prototype should
test rather than only demonstrating success; this file is that list plus the
conditions discovered in practice, with what is known about each.

The system's response to failure may matter more than marginal improvements in
ideal-condition accuracy.

**Status key:** ✅ tested · ⚠️ partly · ❌ untested

---

## 1. Framing and position

| Condition | Status | What is known |
|---|---|---|
| Participant too close | ✅ | Legs below the frame. Two early takes largely wasted. `setup` framing check now catches it live. |
| Participant too far | ❌ | `MOVE CLOSER` exists but has not been triggered in a real take. |
| Feet outside frame | ✅ | Ankles clipped 19–26% of frames in early takes; ankle confidence drops to 0.75. |
| Head outside frame | ⚠️ | Seen incidentally (nose above frame 5–6%), never tested deliberately. |
| Participant partly out of frame sideways | ❌ | |
| Participant moves about the room mid-session | ✅ | Broke calibration completely — a session counted zero. Fixed by cluster calibration, a trailing window, and resetting after a tracking loss. |
| Camera moved during a session | ❌ | Likely to behave like the above, but unverified. |

## 2. Movement

| Condition | Status | What is known |
|---|---|---|
| Slow repetitions | ✅ | `sts_slow_001`: 5.5 and 6.4 s repetitions counted correctly. |
| Fast repetitions | ✅ | 1.8 s repetitions counted correctly. |
| Partial stand | ✅ | Four abandoned stands in `sts_awkward_001`, all now partials. Two were counted as complete before the standing-dwell rule: an abandoned stand held 0.30s where 43 genuine ones all held at least 1.00s. |
| Pause mid-movement | ❌ | **Known weakness.** Rising is confirmed by upward velocity, so pausing part-way through a rise drops the confirmation and RISING may never be entered. |
| Hand support / pushing off the thighs | ❌ | No detection of support use at all yet. |
| Sitting down heavily | ⚠️ | `rapid_descent` exists and is participant-relative, but has never fired on real movement. |
| Using an armrest | ❌ | |
| Shuffling forward on the seat first | ❌ | |
| Extra unrelated movement | ❌ | |
| Failed attempt — tries and cannot rise | ❌ | |
| Standing up for a reason other than the exercise | ✅ | **The engine counts movements, not intentions.** A participant who stood up to finish and switch the machine off produced two complete stand-sit cycles, indistinguishable from repetitions. Not an algorithm fault: the exercise ends when the participant signals, so the signal must come before they get up. |

## 3. Environment and lighting

| Condition | Status | What is known |
|---|---|---|
| Poor lighting | ❌ | |
| Strong backlight | ❌ | |
| **OS-level camera effects** | ⚠️ | See below. Discovered 16 August 2026. |
| Patterned or dark clothing | ❌ | |
| Chair variation | ❌ | One chair used throughout. |
| Chair obscuring the legs | ❌ | |
| Background clutter | ⚠️ | Present incidentally in all takes; never varied deliberately. |

### OS-level camera effects

**macOS Edge Light** turns the display borders into a virtual ring light
whenever any application activates the camera. It is applied by the operating
system, not requested by the application, and it appears and disappears exactly
as our code opens and closes the camera.

This matters more than it first appears. **The participant's illumination stops
being independent of the application.** Lighting becomes a function of whether
our software is running, which is precisely the variable a home-environment
test is meant to hold still.

The same concern applies to the rest of the family:

| Effect | What it changes |
|---|---|
| Edge Light | Illumination of the participant |
| Studio Light | Brightness of the subject relative to the background |
| Centre Stage | Framing — the camera pans and crops to follow the person |
| Portrait / background blur | The image the pose model receives |

Centre Stage is the most alarming of these for this project: it would move the
frame during an exercise, which is indistinguishable from the participant
moving, and would corrupt participant-relative calibration in exactly the way
walking about the room did.

**What to do about it**

- Turn these effects **off** while developing, testing and recording. The
  camera control in the macOS menu bar exposes them while the camera is live.
- Note in a recording's `notes` field whether any were active.
- The browser recorder now stores `MediaStreamTrack.getSettings()` in the
  recording metadata, which captures what the browser will admit about the
  camera's configuration. It does not report Edge Light, so this is a partial
  measure, not a solution.
- Any future participant-facing product will have to either detect these or
  instruct people to disable them, because a participant at home will not
  know they are on.

**Unresolved:** we have no way to detect from inside the application that an OS
effect is active. Every recording made so far predates this discovery, and none
of them records whether Edge Light was on.

## 4. Multiple subjects and interference

| Condition | Status | What is known |
|---|---|---|
| Another person enters frame | ❌ | `num_poses=1`, so a second person is not detected at all. |
| Pet enters frame | ❌ | |
| Mobility aid present | ❌ | Objects are not modelled; a frame or stick is not part of the pose. |

## 5. System and capture

| Condition | Status | What is known |
|---|---|---|
| Camera misreports frame rate | ✅ | Observed: claimed 15 fps, delivered 29.4. Now measured rather than trusted. |
| Frame rate varies during a session | ✅ | 27.9–29.9 fps in Python, 74.8 fps in the browser. The calibration window was in frames, so at 74.8 fps it spanned 4.0s rather than 10.0s and an 11.8s stand emptied it. Now in seconds, like the filters. |
| Tracking lost mid-repetition | ✅ | The repetition is abandoned uncounted, not scored against the participant. |
| Dropped frames / long gaps | ✅ | Velocity is not computed across a gap beyond `maximum_elapsed_ms`. |
| Different camera hardware | ❌ | One webcam throughout. |
| Different runtime | ✅ | The browser negotiates 30–75 fps where Python gets 30. Higher rates exposed the frame-counted calibration window. Both load the identical model file. |

---

## How to use this list

When recording, pick a condition that is untested and reproduce it
deliberately, then add the take to the regression dataset with the true count
in the case file. A case the algorithm handles **badly** is worth more than
another clean one.

Update the status and the "what is known" column when a condition is tested,
so the gap between what has been demonstrated and what has been claimed stays
visible.
