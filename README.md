**# Edge-AI Traffic Analytics, Vehicle Flow Counting & Violation Detection Engine**

A working traffic-camera analytics engine: vehicle detection + tracking, multi-lane

directional counting, automated violation detection (wrong-way / red-light /

illegal lane cut-in), MQTT + FastAPI telemetry, a live web dashboard, and

WhatsApp critical-alert hooks. Built to run on a laptop/dev machine for testing

and on Raspberry Pi 4/5 (64-bit) for edge deployment.

## 📸 System Preview

### Live Traffic Operations Console

![Live Traffic Operations Console](docs/screenshots/live-traffic-operations-console.png)

The live operations console provides real-time visibility into vehicle detection, tracking IDs, traffic counts, lane activity, violations, and incident logs.

### Automated Traffic Violation Alert

![Automated Traffic Violation Alert](docs/screenshots/traffic-violation-alert.png)

Detected traffic violations can trigger structured alerts containing the violation type, vehicle type, track ID, severity, timestamp, and supporting evidence.

**## What's actually in this build (read this first)**

Everything below **\*\*was run and verified\*\***, most recently against the bundled

sample clip (\`data/sample_video/demo_traffic.mp4\` — real, unannotated,

BSD-3-licensed motorway footage from the Qengineering reference repo) on

this dev machine's CPU, plus a live Windows test pass:

\- ✅ Real-time detection with YOLOv8n (COCO-pretrained, no custom training

  needed — Car/Truck/Bus/Motorbike are already COCO classes)

\- ✅ Multi-object tracking with stable IDs (Ultralytics' built-in ByteTrack)

\- ✅ Multi-lane directional counting (tripwire line-crossing, inbound/outbound)

\- ✅ Wrong-way driving detection — verified with 0 false positives across the

  entire 2,501-frame clip, AND verified to correctly fire (22/41 flagged) on

  a real-footage-reversed test clip (see "Why three separate demos" below)

\- ✅ Red-light jumping detection — signal-state-driven logic verified correct

  via a controlled demo on real footage (see below)

\- ✅ Illegal lane cut-in detection — logic verified correct via dedicated

  unit tests (\`tests/test_lane_cutin.py\`), since it doesn't occur naturally

  in the bundled clip's orderly traffic

\- ✅ Evidence snapshot saving per violation (annotated crop, timestamp, and

  speed estimate when available)

\- ✅ Speed estimation — distance/time method between two calibrated lines

  (same principle real average-speed-check cameras use). Unit-tested

  (\`tests/test_speed_estimator.py\`) and verified on the real clip: 86

  vehicles got a completed reading over a 1,500-frame run, with plausible

  values (18-60 km/h, rising as an initial traffic queue clears — matches

  what's visible in the footage). The bundled \`distance_m\` calibration is

  **\*\*illustrative, not precisely surveyed\*\*** — see \`config/config.yaml\` for

  how to calibrate it against a real measured distance for your camera.

\- ✅ MQTT telemetry (tested live against a local Mosquitto broker — metrics +

  violations + online/offline status all confirmed publishing)

\- ✅ FastAPI service: \`/health\`, \`/api/metrics\`, \`/api/violations\`,

  \`/video_feed\` (MJPEG), \`/ws/live\` (WebSocket) — all tested and responding,

  including a full live dashboard test on Windows

\- ✅ Live web dashboard (single HTML file, no build step) consuming the

  WebSocket feed

\- ✅ WhatsApp alerting (Evolution API, self-hosted via Docker) — \*\*real phone

  delivery confirmed\*\*: a live Evolution API + PostgreSQL + Redis stack was

  stood up, a real WhatsApp number was linked via QR code, and actual

  violation alerts (text + evidence image) were received on a real phone

  during a live pipeline run — not just a mock-server request-shape check

\- ✅ CSV logging of every count + violation event

\- ✅ Annotated output video

**\*\*What's still unverified, and why:\*\***

\- The **\*\*>25 FPS on Raspberry Pi\*\*** target. On this dev machine's CPU the

  pipeline runs at \~9-10 FPS at 640px (no GPU here). Export to NCNN/TFLite

  (\`scripts/export_edge_model.py\`) and re-run \`scripts/benchmark_fps.py\` \*on

  the actual Pi\* — CPU throughput doesn't transfer between machines.

\- **\*\*Motorcycles.\*\*** The bundled clip is UK motorway footage and genuinely

  doesn't contain any (checked across the full clip at a lowered confidence

  threshold — 756 Car / 9 Truck / 9 Bus detections, 0 Motorbike). The

  detector already supports Motorbike (it's COCO class 3, zero code

  changes needed) — if you have footage with motorcycles/bikes, drop it in

  and it'll be detected immediately. No properly-licensed clip with

  motorcycles was available to source and bundle here (see below).

**## Why three separate demos, not one video**

A client-friendly request is "one video showing every violation type

working." Being direct about why that's not what's shipped: genuine

wrong-way driving, a real controlled traffic signal, and erratic lane-cutting

essentially never co-occur in ordinary, legally-usable traffic footage — and

none of it can be fabricated with fake/drawn vehicles, because YOLO won't

detect a drawn rectangle as a car. So each violation type is demonstrated the

most honest way that's actually possible with real vehicle imagery:

\| Violation | Demo | Why |

\|---|---|---|

\| Wrong-way | Real footage, time-reversed | Genuine wrong-way footage isn't realistically obtainable; reversing real traffic creates genuinely-backward real vehicles |

\| Red-light | Real footage + manually-controlled signal window | The clip has no real traffic light; the logic is signal-\*\*state\*\*-driven, not a light-color reader, so a controlled window proves the same logic a real signal feed would use |

\| Illegal lane cut-in | Unit tests, not a video | Doesn't occur in this orderly real footage; the algorithm is proven correct directly instead of faked |

All three are documented in detail, including exact result counts, in

\`samples/README.md\`. This is slower than shipping one flashy video, but

everything in this package is either real footage or an explicitly-labeled,

disclosed test methodology — nothing pretends to be something it isn't.

**## Two real bugs found and fixed during testing**

1\. **\*\*Wrong-way lane-geometry bug.\*\*** Normal traffic crossing between two

   "carriageway" polygons split by a straight vertical line got misjudged

   against the wrong lane's allowed direction once the camera's perspective

   converged near the horizon. Produced a 17%, then 7.5%, false-positive

   rate before being properly root-caused with a dedicated trajectory-tracing

   script and fixed by redrawing the lane polygons as perspective-correct

   trapezoids. Re-verified: 0 false positives across the full 2,501-frame clip.

2\. **\*\*Lane cut-in geometry drift (same root cause, different detector).\*\***

   Individual in-carriageway lane polygons had the same straight-line

   perspective issue, causing every vehicle's \*\*lane assignment\*\* to drift

   Lane-1→2→3→4 as it receded into the distance — indistinguishable from a

   real lane change if you just count "assignment changed." Fixed by only

   counting a transition as suspicious when it reverses direction or jumps

   more than one lane — smooth single-direction drift (what perspective

   produces) is now correctly ignored. Verified with unit tests plus a

   full-clip scan (0 false positives).

A third issue was **\*\*CPU inference non-determinism\*\***, not a design bug: two

back-to-back runs of the identical code/config/video produced different

track IDs and, occasionally, an ID-swap after two vehicles crossed paths —

a well-known hard problem in multi-object tracking generally, not unique to

this codebase. Mitigated by discarding a track's trajectory history across

any single frame-to-frame jump larger than a real vehicle could plausibly

make (\`max_step_displacement_px\` in config.yaml) — this is a real

robustness improvement for occlusion-heavy scenes generally, not just a

one-off fix.

The same non-determinism showed up again in \`scripts/demo_red_light_scenario.py\`:

a narrow \~1-second RED window that reliably caught 3 vehicles on one machine

caught only 1 on a second machine (same code, same video, different run) —

not a bug, just a demo relying on an overly tight timing margin. Widened the

window to \~6.7 seconds so it robustly catches multiple vehicle types

regardless of minor tracking timing shifts; re-confirmed identical results

(7 vehicles: Truck, Bus, 5 Cars) on both machines afterward.

**## Jetson, WhatsApp, and camera-specific notes**

\- **\*\*Jetson deployment\*\*** — the code runs on Jetson (Ultralytics + OpenCV both

  support it), and the TensorRT export path is built

  (\`scripts/export_edge_model.py --format engine\`), but a \`.engine\` file

  must be compiled on the Jetson itself (TensorRT builds aren't portable

  across machines) — see "Deploying to NVIDIA Jetson" below. No Jetson

  board was available here to verify real FPS on.

\- **\*\*WhatsApp delivery\*\*** — real, confirmed working. A self-hosted Evolution

  API stack (Evolution API + PostgreSQL + Redis, via Docker Compose) was

  stood up, a real WhatsApp number linked by QR code, and actual violation

  alerts landed on a real phone during a live pipeline run — text alerts and

  evidence-image alerts both confirmed. Disabled by default in the shipped

  \`config.yaml\` (\`telemetry.whatsapp.enabled: false\`) so a fresh setup never

  fires alerts at someone else's number by accident — flip to \`true\` and

  fill in your own instance/credentials to go live. See "Connecting WhatsApp

  alerts" below for the full setup (including the Docker Compose stack).

\- **\*\*Auto-start on boot\*\*** — \`start_dashboard.bat\` and \`setup_autostart.bat\`

  (project root) register the live dashboard server with Windows Task

  Scheduler so it starts automatically on login, no manual command needed.

  See "Running automatically on startup" below.

\- **\*\*The bundled demo clip\*\*** (\`data/sample_video/demo_traffic.mp4\`) is raw,

  unannotated motorway footage from the Qengineering reference repo

  (BSD-3 licensed) — no pre-existing bounding boxes baked in, so every box

  you see in the output is this engine's own detection. Lanes/lines/sub_lanes

  in \`config/config.yaml\` are pre-calibrated for this specific clip's

  640x480 camera angle. \`red_light\` is disabled by default for this clip

  since it's open motorway footage with no real signal — see "Why three

  separate demos" above for how it's still validated.

Every real camera install needs \`scripts/calibrate.py\` run once to redraw

lanes/lines/zones for that specific angle — this is true of every

traffic-CV system in the research doc, not a shortcut taken here.

Everything else is real, runnable code — not stubs. The NCNN and TFLite

export paths (\`scripts/export_edge_model.py\`) were run and verified

end-to-end on this CPU-only machine: exported, reloaded, run through

\`benchmark_fps.py\`, and run through the full pipeline against the sample

video — all confirmed working (NCNN: \~49 FPS on this x86 CPU at 320px;

TFLite int8: \~110 FPS on this x86 CPU at 320px — again, these are \*this dev

machine's\* numbers, not Pi numbers). One transient issue was found and

fixed: on this environment's torch version, the TFLite export occasionally

throws an error from an unrelated post-export validation step

\*\*after\*\* the model file has already been written correctly — the script now

detects this and continues if the output file exists rather than failing.

The **\*\*Jetson TensorRT export\*\*** (\`--format engine\`) could not be executed at

all here — this sandbox has no NVIDIA GPU/CUDA (\`torch.cuda.is_available()\`

returns False), and TensorRT export hard-requires one. The code path exists

and follows Ultralytics' documented export API the same way the working

NCNN/TFLite paths do, but it has only been checked for syntax/argument

correctness, not run. It needs to be tried on a real Jetson to confirm it

actually works.

\---

**## Project layout**

\`\`\`

traffic-engine/

├── app/
│   ├── config.py          # loads config.yaml (+ env var overrides)
│   ├── geometry.py         # point-in-polygon / line-crossing / angle math
│   ├── detector.py         # YOLO detection + ByteTrack wrapper
│   ├── flow_counter.py     # multi-lane directional counting
│   ├── signal_state.py     # traffic-signal phase (simulator/manual/mqtt)
│   ├── violations.py       # wrong-way / red-light / lane cut-in detectors
│   ├── pipeline.py         # orchestrates capture -> detect -> count -> telemetry
│   ├── shared_state.py     # thread-safe bridge between CV loop and API
│   ├── telemetry/
│   │   ├── events.py           # evidence snapshot saving
│   │   ├── mqtt_publisher.py   # MQTT publisher
│   │   └── whatsapp_alerts.py  # Evolution API WhatsApp client
│   ├── api/main.py         # FastAPI service (REST + WebSocket + MJPEG)
│   └── dashboard/index.html # live ops dashboard (single file)
├── scripts/
│   ├── run_pipeline.py      # main CLI entrypoint
│   ├── benchmark_fps.py     # measure real detector FPS on current hardware
│   ├── export_edge_model.py # export to NCNN/TFLite for Raspberry Pi
│   ├── calibrate.py         # grab a reference frame + pixel grid for site calibration
│   └── demo_red_light_scenario.py  # controlled real-footage red-light demo (see samples/README.md)
├── config/config.yaml       # all tunables: lanes, lines, zones, telemetry
├── data/sample_video/       # demo clip(s) for testing without a camera
├── docker/                  # Dockerfile + docker-compose (engine + Mosquitto)
├── evolution-docker-compose.yml  # Evolution API + Postgres + Redis (WhatsApp alerts)
├── start_dashboard.bat      # Windows: activate venv + start the live server
├── setup_autostart.bat      # Windows: run once (as admin) to auto-start on login
├── requirements.txt         # dev/desktop dependencies
└── requirements-rpi.txt     # Raspberry Pi dependencies

\`\`\`

\---

**## Quick start (desktop / dev machine)**

\`\`\`bash

cd traffic-engine

python3 -m venv venv && source venv/bin/activate

pip install -r requirements.txt

\# 1) Headless test run against the bundled sample video (writes annotated.mp4 + stats.csv)

python -m scripts.run_pipeline --config config/config.yaml --max-frames 300

\# 2) Or run it live with the dashboard + telemetry API:

python -m scripts.run_pipeline --serve --config config/config.yaml

\# then open http\://localhost:8000/

\`\`\`

MQTT is optional for a first run — if no broker is reachable at

\`telemetry.mqtt.host:port\`, the publisher logs a warning once and the rest of

the pipeline keeps working normally. To see real MQTT traffic:

\`\`\`bash

\# separate terminal

sudo apt install mosquitto mosquitto-clients   # or: brew install mosquitto

mosquitto -d

mosquitto_sub -h localhost -t 'traffic/intersection-1/#' -v

\`\`\`

**## Using your own camera / video**

Edit \`config/config.yaml\`:

\`\`\`yaml

video:

  source: 0                 # USB webcam index, "picam" on a Pi, or an RTSP URL / file path

\`\`\`

Then **\*\*recalibrate lanes and lines for your camera angle\*\*** — this is required,

not optional, for correct counting/violation logic:

\`\`\`bash

python -m scripts.calibrate --source 0

\# open outputs/calibration_frame.jpg, read off pixel coordinates,

\# paste them into config/config.yaml under lanes / counting_lines / violations

\`\`\`

To reproduce the wrong-way demo yourself, \`data/sample_video/wrongway_test_clip.mp4\`

is included (the real, reversed segment described in \`samples/README.md\`) —

point \`video.source\` at it and run the pipeline normally.

\---

**## Deploying to Raspberry Pi 4/5 (64-bit)**

\`\`\`bash

sudo apt update && sudo apt install -y python3-opencv python3-picamera2 mosquitto mosquitto-clients

pip install -r requirements-rpi.txt --break-system-packages

\# Export the model to an edge-friendly format (do this once, on the Pi or a dev machine)

python -m scripts.export_edge_model --format ncnn --imgsz 320

\# -> produces yolov8n_ncnn_model/

\# Point config.yaml at it

\#   model:

\#     weights: "yolov8n_ncnn_model"

\#   video:

\#     imgsz: 320

\# Confirm real throughput on THIS board before going live

python -m scripts.benchmark_fps --weights yolov8n_ncnn_model --imgsz 320 --frames 200

\# Run for real, with the dashboard reachable on the network

python -m scripts.run_pipeline --serve --config config/config.yaml

\`\`\`

If 320px NCNN still doesn't clear \~25 FPS on your specific Pi board/camera

combo, the next lever is \`video.frame_skip\` in config.yaml (process every

2nd frame) — counting/violation logic tolerates this fine since tracking

carries IDs across skipped frames.

**### Docker (bundles Mosquitto + the engine)**

\`\`\`bash

cd docker

docker compose up --build

\`\`\`

\---

**## Deploying to NVIDIA Jetson (Orin / Xavier / Nano)**

Jetson uses TensorRT instead of NCNN/TFLite for its fastest inference path.

Two important differences from the Pi flow above:

1\. **\*\*Torch/torchvision must match your JetPack version.\*\*** NVIDIA ships its

   own builds for Jetson (the regular pip wheels don't include Jetson GPU

   support) — install those first, following NVIDIA's official Jetson +

   Ultralytics setup guide for your exact JetPack version before installing

   the rest of \`requirements.txt\`.

2\. **\*\*The TensorRT export MUST run on the Jetson itself\*\***, not on a dev

   laptop — a \`.engine\` file is compiled for the exact GPU + TensorRT + CUDA

   versions of the machine that built it and will not run anywhere else.

\`\`\`bash

\# On the Jetson, after JetPack + the matching torch/torchvision are installed:

pip install -r requirements.txt

\# Export (run this ON the Jetson):

python -m scripts.export_edge_model --format engine --imgsz 320 --half

\# -> produces yolov8n.engine

\# Point config.yaml at it

\#   model:

\#     weights: "yolov8n.engine"

\#   video:

\#     imgsz: 320

\# Confirm real throughput on this board

python -m scripts.benchmark_fps --weights yolov8n.engine --imgsz 320 --frames 200

python -m scripts.run_pipeline --serve --config config/config.yaml

\`\`\`

\---

**## Connecting WhatsApp alerts (Evolution API)**

**\*\*Already verified end-to-end, on a real phone.\*\*** A full self-hosted stack

(Evolution API + PostgreSQL + Redis) was run via Docker Compose, a real

WhatsApp number was linked by scanning a QR code in Evolution API's own

manager dashboard, and actual violation alerts — both plain text and

evidence-image-attached — were confirmed arriving on that phone during a

live pipeline run. This is a genuine working integration, not just a

request-shape check.

**### 1. Stand up Evolution API**

Evolution API needs a Postgres database and (for reliable operation) Redis —

it will not run standalone. Use the bundled \`evolution-docker-compose.yml\`

(project root):

\`\`\`powershell

docker compose -f evolution-docker-compose.yml up -d

docker ps   # confirm evolution-api, evolution-postgres, evolution-redis are all "Up"

\`\`\`

This starts Evolution API on \`http\://localhost:8080\` with API key

\`my-secret-key-123\` (change this before any real deployment — it's a demo

value, see "Security note" below).

**### 2. Link a WhatsApp number**

1\. Open \`http\://localhost:8080/manager\` in a browser, log in with the API key.

2\. Create a new instance (Channel: **\*\*Baileys\*\***) — name it e.g. \`traffic-alerts\`.

3\. Click **\*\*Get QR Code\*\***, then on the phone: WhatsApp → Settings → Linked

   Devices → Link a Device → scan it.

4\. Status should flip to **\*\*Open/Connected\*\***.

**### 3. Point the engine at it**

In \`config/config.yaml\` under \`telemetry.whatsapp\`:

\`\`\`yaml

telemetry:

  whatsapp:

    enabled: true

    evolution_api_url: "http\://localhost:8080"

    evolution_api_key: "my-secret-key-123"   # match whatever you set in the compose file

    instance: "traffic-alerts"

    to_number: "923XXXXXXXXX"                 # E.164 without '+'

    alert_on: ["wrong_way", "red_light", "illegal_lane_change"]

    min_seconds_between_alerts: 15

\`\`\`

Critical violations will now push a WhatsApp message with the evidence

snapshot attached, rate-limited by \`min_seconds_between_alerts\` so a bad

minute doesn't spam the recipient.

**### Security note before a real deployment**

\`my-secret-key-123\` and the Postgres password in

\`evolution-docker-compose.yml\` are demo values used during testing — change

both to strong, unique values before pointing this at a real WhatsApp

number or leaving it running anywhere reachable. Also swap \`to_number\` from

any personal test number to the actual intended recipient (e.g. the

operations/security desk that should receive real violation alerts).

**### Safe default**

The shipped \`config.yaml\` has \`telemetry.whatsapp.enabled: false\` and

placeholder credentials — a fresh checkout never sends alerts to anyone

until you deliberately configure and enable it.

\---

**## Running automatically on startup (Windows)**

Two scripts (project root) set the live dashboard server to start on its

own, no manual command needed each time:

\- **\*\*\`start_dashboard.bat\`\*\*** — activates the venv and starts

  \`scripts.run_pipeline --serve\`. Waits 20s first so Docker/network have

  time to come up after login. Double-click to test it manually.

\- **\*\*\`setup_autostart.bat\`\*\*** — run **\*\*once\*\***, as Administrator (right-click →

  "Run as administrator"), to register \`start_dashboard.bat\` with Windows

  Task Scheduler under an "at logon" trigger.

To undo: \`schtasks /Delete /TN "TrafficAnalyticsEngine" /F\`

Note: this starts the Python/FastAPI server, not the Evolution API Docker

stack — set Docker Desktop's own "start on login" option (Settings →

General) if WhatsApp alerts should also survive a reboot unattended.

\---

**## Tuning violation sensitivity**

All thresholds live in \`config/config.yaml\` under \`violations:\` — e.g.

\`angle_threshold_deg\` and \`confirm_frames\` for wrong-way driving, or

\`max_switches_allowed\` / \`window_seconds\` for lane cut-ins. If you see false

positives on a new camera, that's almost always a calibration/threshold issue,

not a code bug — start with \`scripts/calibrate.py\` and widen the thresholds

before assuming the detector is broken.

\---

**## Sample outputs**

\`samples/\` contains real output from actual runs of this engine — annotated

videos, stats CSVs, and evidence snapshots for the main pipeline, the

wrong-way demo, and the red-light demo, each with exact result counts. See

\`samples/README.md\` for what each one proves and how it was produced.

\---

**## Reference repos this build draws on**

Per the original research brief: Qengineering's Traffic-Counter-RPi_64-bit

(RPi + MQTT pattern), sopheakchan's realtime-vehicle-detection (line-crossing

counting pattern), and Prince-IISc-CalUniv's Edge-AI-Traffic-Analytics

(violation/congestion/speed concepts) were all cloned and reviewed while

building this. Wrong-way / red-light / lane-cut-in logic specifically isn't

present verbatim in any of those repos (none of the three implement it) —

it's been designed fresh here to match the ticket's requirements, using the

same tracking/geometry foundation those repos establish.
