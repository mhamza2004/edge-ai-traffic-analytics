# Sample Outputs — What Each One Proves

Three separate demo runs, because one real video can't honestly show every
violation type (see the main README's "Why three separate demos" section).
All three use the SAME real vehicle detection + tracking pipeline — only the
video source and (for #3) the signal-state input differ.

## 1. Main pipeline output — `1_main_pipeline_output.mp4` / `1_main_pipeline_stats.csv`

The bundled `demo_traffic.mp4` (real, unannotated, BSD-3-licensed motorway
footage), run through the full pipeline: detection, tracking, multi-lane
counting, and all three violation detectors active.

**Result: 133 vehicles counted, 0 violations of any type.** That's the
correct, verified result for this footage — it's ordinary flowing motorway
traffic with no real wrong-way driving, no real traffic signal, and no
genuinely erratic lane-cutting in it. Two real bugs were found and fixed to
get to this clean result (see main README): a lane-geometry miscalibration
that mis-flagged normal traffic as "wrong way," and a lane-cut-in false
positive from the same kind of geometry drift. Both are fixed and re-verified
against the full 208-second / 2,501-frame clip, not just this 1,500-frame
sample.

## 2. Wrong-way detection — `2_wrongway_demo_output.mp4` / `2_wrongway_demo_stats.csv`

Since genuine wrong-way driving essentially never appears in ordinary traffic
footage, this clip is a **real 37-second segment of the same motorway video,
played in reverse**. Every vehicle in it is real; time-reversing real forward
traffic makes it genuinely travel backward in the frame, which is exactly
what the wrong-way detector is supposed to catch. This is a standard,
disclosed testing technique — not a fabricated video, and not something to
present as "found this vehicle driving the wrong way on camera."

**Result: 22 of 41 vehicles flagged wrong-way.** (Not 41/41 — vehicles too
small/distant, or with too short a track history, are correctly skipped per
the detector's own thresholds; see `wrongway_evidence/` for saved snapshots.)

## 3. Red-light violation — `3_redlight_demo_output.mp4`

The system's red-light logic is **signal-state-driven**, not a computer-vision
traffic-light-color reader — it checks "did a vehicle cross the stop-line
while `SignalState.is_red()`," where the signal state comes from a timer
simulator, a manual override, or an external MQTT feed (see
`app/signal_state.py`). The bundled motorway clip has no real traffic light
controlling it, so running the plain timer simulator against continuous
real traffic produces a misleading ~35% "violation" rate — not a detection
bug, just a mismatch between a signal-controlled-intersection assumption and
open-motorway footage.

`scripts/demo_red_light_scenario.py` instead holds the signal GREEN for the
whole real clip except one deliberately chosen ~6.7-second window, showing
exactly the vehicles that genuinely cross the stop-line during that window
getting flagged, and everything else passing normally — a controlled,
disclosed demonstration on real footage, not a fabricated scenario. (The
window was widened from an initial ~1 second after testing on a second
machine showed CPU inference isn't perfectly deterministic run-to-run — a
narrow window could catch a different subset of vehicles on a different
run; the wider window reliably catches multiple vehicle types every time.)

**Result: 7 vehicles flagged (1 Truck, 1 Bus, 5 Cars) — precisely the ones
crossing during the deliberately-set RED window.** Re-confirmed identical on
a second machine. See `redlight_evidence/`.

For a real signalized intersection, point `signal_source` at `mqtt` (fed by
the actual signal controller) instead of the simulator, and this same logic
applies directly with no code changes.

## Illegal lane cut-in — no video, unit tests instead

This one genuinely doesn't occur anywhere in the 208-second real clip —
orderly flowing motorway traffic essentially never shows a vehicle reversing
direction across lanes within a few seconds. Rather than fabricate a video
for it, the detection logic itself is validated directly with
`tests/test_lane_cutin.py`: it proves the algorithm correctly ignores smooth
same-direction lane drift (which is what a converging-perspective camera
produces for a car staying in one real lane) and correctly flags genuine
back-and-forth weaving or a multi-lane jump. Run it with:

```bash
python -m tests.test_lane_cutin
```

If you have real footage with an actual aggressive lane-cut incident, drop
it in and recalibrate `sub_lanes` in config.yaml — the detector will work on
it immediately, no code changes needed.

## Speed estimation

Uses a distance/time method: two lines a known real-world distance apart,
speed = distance / (real time between crossing line A and line B) — the
same principle real average-speed-check cameras use. Verified with unit
tests (`tests/test_speed_estimator.py`) and on the real clip: 86 vehicles
got a completed speed reading over a 1,500-frame run of the main pipeline,
values ranging ~18-60 km/h and rising over time — matches the visible
traffic queue clearing earlier in the footage.

The `2_wrongway_demo_output.mp4` and `3_redlight_demo_output.mp4` evidence
snapshots mostly show no speed value: those violations happen very early in
each clip, before the violating vehicle has crossed both lines of the
speed-check zone, so no measurement had completed yet at the moment of the
violation. This is expected given those two demos' specific timing, not a
bug — see the main README for how the method works and where it succeeds
(the main pipeline run above).

The bundled `distance_m: 18.0` calibration (`config/config.yaml`) is
**illustrative**, not a precisely surveyed real-world measurement — replace
it with an actual measured distance for your own camera before treating
readings as accurate.
