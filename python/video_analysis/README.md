# Video analysis and BoT-SORT tracking

The default backend is now the validated local YOLOX/FastReID/BoT-SORT pipeline.
See [BoT-SORT deployment](BOTSORT_DEPLOYMENT.md) for current startup, shared model
workers, timing, rollout and rollback. The historical detection-only behavior
below is available with `VIDEO_ANALYSIS_ALGORITHM=deepsort` and its Python environment.

The lanhu dashboard plays the four original MediaMTX WebRTC streams. This service
reads the corresponding RTSP streams independently and sends detection JSON to a
single WebSocket per page. Each camera has its own Canvas, video status and AI
status. One dashboard button toggles annotations for all four cameras. Fullscreen
includes the overlay and compact toolbar. The shared toggle is above the grid
and moves into the active fullscreen view, still controlling all four cameras.
The service sends structured boxes; optional business delivery registers complete
historical results through the business API. Synchronized
clients also receive the clean inference input image. The dashboard defaults to continuous realtime WebRTC playback with asynchronous
metadata overlays that expire after at most one second. Same-frame JPEG playback is opt-in. Module
responsibilities, configuration and validation limits are in [SYNC_PLAYBACK.md](SYNC_PLAYBACK.md).

## Deployment

Unified input and background recording are enabled with
`VIDEO_ANALYSIS_RECORDING_ENABLED=true` and explicit source UUID mappings.
The local launcher uses the existing `botsort39` interpreter and adds this
checkout's `.run/media-deps` to `PYTHONPATH` for PyAV. Recording packets and
decoded public frames share one connection and media clock; MediaMTX playback
remains independent. File and API configuration are described in
[the stage-one integration guide](../../docs/README.md#统一输入与后台录像配置).

The versioned `scripts/start-local.sh` launcher defaults to shared mode. The primary
checkout `/data/nfs_storage/hxjm` owns the MediaMTX relay and exactly one Uvicorn supervisor
with one YOLOX-X/FastReID model subprocess. Worktrees subscribe through same-origin
Vite proxies. Stopping a developer application does not stop the shared services.
See [BoT-SORT deployment](BOTSORT_DEPLOYMENT.md) for startup, ownership and maintenance.

The shared launcher selects GPU 0 by default (`SHARED_BOTSORT_GPU` overrides it);
the device also serves VLLM workloads and is not reserved exclusively. It fixes
OpenCV compute threads at 8, Torch/OpenMP/BLAS and per-camera decoder threads at 1,
and sets `MALLOC_ARENA_MAX=2`, `MALLOC_TRIM_THRESHOLD_=131072` before process startup.
Model loading and inference do not use a host available-memory threshold to pause
workers. Actual allocation failures, worker exits and inference timeouts are
handled by the worker supervisor and its retry policy.

The shared detector defaults to a fixed `1×3×800×1440` FP16 CUDA Graph. It verifies
capture/replay against the ordinary model and clones output before YOLOX's in-place
postprocessing. Set `SHARED_BOTSORT_CUDA_GRAPH=0` and restart the shared service to
disable it. Byte-table preprocessing preserves the original float64-to-float32
rounding exactly; cached YOLOX decode grids and vectorized GMC point filtering
retain their original values and matching rules. FastReID no longer imports its
unused training entry points. Input size, thresholds, ReID, small-target recovery
and crossing protection retain their existing settings.

Current automated checks cover 47 algorithm tests, 36 analysis-service tests and
9 shared-manager tests. Numerical equivalence and synthetic tests still require
regression on the original small-target/crossing videos to assess ID stability.
Same-frame throughput must be measured from changing paired JPEG frame IDs;
raw WebRTC playback FPS does not measure inference throughput.

`VIDEO_ANALYSIS_MODE=local` explicitly starts an independent experimental analysis
service with that worktree's ignored `.run/video-analysis.env` settings. Only in
this local mode does `START_VIDEO_ANALYSIS=no` disable analysis startup. Models are
local assets and are never downloaded by the launcher. Run one Uvicorn worker;
multiple replicas would create independent schedulers and duplicate inference.

The following configuration reference is for direct/experimental service startup.
Historical YOLOv5/SAHI options below apply only to `VIDEO_ANALYSIS_ALGORITHM=deepsort`.

The default cameras are camera_1 through camera_4. Override them with a JSON map
(up to 16 cameras), for example:

```bash
export VIDEO_ANALYSIS_CAMERAS='{"camera_1":"rtsp://127.0.0.1:18554/live/camera_1","camera_2":"rtsp://127.0.0.1:18554/live/camera_2"}'
```

An explicit legacy `VIDEO_ANALYSIS_RTSP_URL` still enables only
`VIDEO_ANALYSIS_CAMERA_ID` for stage-one deployments; remove it when switching to
four cameras. The dashboard has four camera slots. Unconfigured slots show a
waiting state in same-frame mode; switch to realtime mode to view their original video.

Set these variables when starting/building lanhu:

```dotenv
VITE_VIDEO_ANALYSIS_MODE=local
VITE_VIDEO_ANALYSIS_ENABLED=true
VITE_VIDEO_ANALYSIS_ORIGIN=http://127.0.0.1:28010
```

`VITE_MEDIA_PORT` selects the MediaMTX WebRTC port. The browser connects to the
same-origin `/ws/detections`. Vite proxies it to the analysis service separately
from the existing business `/ws`. Production needs an equivalent reverse proxy.

| Variable | Default | Purpose |
| --- | --- | --- |
| VIDEO_ANALYSIS_WORKERS | 1 | Maximum on-demand model subprocesses, 1–4; each owns independent camera trackers |
| VIDEO_ANALYSIS_INTERVAL_SECONDS | 0.05 (BoT-SORT), 1 (legacy) | Minimum interval between attempts on each camera/task |
| VIDEO_ANALYSIS_INFERENCE_TIMEOUT_SECONDS | 10 | Inference response deadline; terminate stuck Worker |
| VIDEO_ANALYSIS_MODEL_TIMEOUT_SECONDS | 60 | Model initialization deadline |
| VIDEO_ANALYSIS_WORKER_RETRY_SECONDS | 5 | Initial per-worker exponential retry delay; resets after successful inference |
| VIDEO_ANALYSIS_WORKER_RETRY_MAX_SECONDS | 120 | Maximum retry delay |
| VIDEO_ANALYSIS_WORKER_IDLE_SECONDS | 60 | Delayed idle model retirement |
| VIDEO_ANALYSIS_FRAME_FRESH_SECONDS | 2 | Maximum decoded-frame age before scheduling |
| VIDEO_ANALYSIS_RESULT_TTL_SECONDS | 3 | Result lifespan measured from frame capture |
| VIDEO_ANALYSIS_DECODE_THREADS | 1 | FFmpeg decoder threads per camera, 1–8 |
| VIDEO_ANALYSIS_OPENCV_THREADS | 4 (shared: 8) | OpenCV compute threads, 1–8; applied after YOLOX imports |
| VIDEO_ANALYSIS_CUDA_GRAPH | 1 | BoT-SORT fixed-shape detector graph; shared launcher uses SHARED_BOTSORT_CUDA_GRAPH |
| VIDEO_ANALYSIS_RECONNECT_SECONDS | 2 | Independent RTSP reconnect delay |
| VIDEO_ANALYSIS_WS_SEND_TIMEOUT_SECONDS | 5 | Disconnect an individual slow browser |
| VIDEO_ANALYSIS_MAX_CLIENTS | 64 | Bound total client subscriptions |
| VIDEO_ANALYSIS_MAX_FRAME_BYTES | 24883200 | Maximum BGR frame bytes (3840×2160×3) |
| VIDEO_ANALYSIS_CACHE_DIR | local .runtime | Model/cache directory |

The service uses up to four slots, capped by the number of configured cameras.
Only cameras with fresh frames are scheduled; unavailable streams never hold a
slot. Each active subprocess loads one reusable model on demand. Increasing Worker count multiplies
model/GPU memory consumption. Browsers never create models or analysis tasks.
The detector reuses `python/deepsort/server.py` model settings and person filtering.
`DEEPSORT_USE_SAHI=false` defaults to full-frame inference; true uses the existing
slice size, overlap, threshold and suppression settings. BGR is converted to RGB
before SAHI inference. Output is capped at 500 person boxes per result.

## Scheduling, bounded memory and recovery

Each camera owns an independent reconnecting capture thread with a single latest
frame. Available model slots scan eligible cameras in round-robin order. A slot
claims at most one analysis for a camera/task and then takes the latest frame.
There is no waiting frame FIFO, no per-browser inference and no duplicate in-flight
work on the same camera/task. A disconnected/stale camera is skipped.

A spawned subprocess owns the model. A slot allocates at most one shared-memory
frame while busy; the parent and that model subprocess share this buffer. IPC
carries a job ID and metadata. The subprocess returns JSON-compatible detections,
without drawing. On inference failure, crash or timeout the supervisor terminates
and reaps the old child, releases its shared memory, rotates the affected camera's
session and loads a replacement only while eligible source frames exist. Other capture threads and browser video connections
continue. With one Worker all AI cameras wait during model reload; configure more
slots if other AI work must continue during a reload. Video always remains independent.

Every subscriber retains at most one status and one detection per camera/task
(eight messages for four cameras). Coalescing retains FIFO key order so a busy
camera cannot starve another camera. Sending runs separately per client with a
deadline. Latest-frame caches, recent metrics, subscriptions and job IPC are bounded.
Service shutdown cancels inference and terminates model processes; capture threads
exit after their configured five-second FFmpeg open/read deadline.

## Protocol

`GET /health` reports per-camera capture/session/counts and per-Worker PID,
generation, model initialization count, restarts and availability.
`/ws/detections` sends per-camera statuses once per second and detections as ready.
Messages identify `camera_id`, `task=deepsort`, `service_session_id`,
`stream_session_id`, monotonically increasing `session_generation`, and
`stream_epoch` (RTSP reconnect). Worker failures rotate the affected analysis
session; service restarts create a new service session and WebSocket connection.
The legacy `stream_session_id` remains an analysis reset token. With shared input,
`input_stream_session_id` identifies the actual video input session and
`tracking_context_id` identifies the tracker state. Resetting a tracker retains
the input session used by recording and historical results.
Only a status establishes a frontend session. Older generations/epochs, mismatched
sessions/tasks/cameras and duplicate frame IDs are rejected. All timers and caches
are separated by camera/task; video components remain mounted during AI updates.

Detections include normalized `xyxy` boxes, `source_width/height`, `frame_id`,
`inference_ms`, `frame_ts_ms`, `completed_at_ms`, `valid_until_ms`, `sent_at_ms`,
and `valid_for_ms`. `timestamp_kind` distinguishes PTS wall estimates from local
decode timestamps; see stage-three limitations below. Zero detections clear boxes
on their matched video frames. Expired or cross-reconnect results are discarded.
The realtime overlay lifetime ceiling is one second; same-frame results retain their own expiry. Original realtime playback
uses approximate alignment. Opt-in same-frame packets bind a clean image to its
own detections instead; see [SYNC_PLAYBACK.md](SYNC_PLAYBACK.md).

## Verification and rollback

```bash
PYTHONPATH=python python -B -m unittest discover -s python/video_analysis/tests -v
cd lanhu
npm test
npm run build
```

Tests cover round-robin scheduling, global concurrency, single in-flight work,
three browsers sharing one scheduler, offline camera recovery, bounded subscriber
queues, stale epochs, responsive status during delayed inference, and actual spawned
child timeout/crash/cancellation cleanup. Frontend tests verify independent routing,
result expiry, old session rejection and existing letterbox coordinate mapping.

Browser acceptance: all four request original `/live/camera_N/whep`, receive matching
results through one socket, and keep the same video elements during AI recovery.
Stop a personal model child with SIGSTOP to simulate a hang: the service should
replace it after the inference deadline, expire overlays, and resume detections while
video time advances. Only signal a PID confirmed to belong to the personal service.

To temporarily restore stage-one coverage, set `VIDEO_ANALYSIS_CAMERAS` to only
camera_1 (all four videos remain raw). To restore the previous full implementation,
revert the stage-two commit once committed, restore the corresponding personal
launcher configuration and restart the personal analysis/frontend services.
`VITE_VIDEO_ANALYSIS_ENABLED=false` restores the older algorithm-first/fallback
playback strategy. This stage has no database migration. Save ignored personal
configuration separately; Git rollback does not restore it.

## Stage three: demand, states and approximate alignment

The playback description below records the earlier approximate renderer. Current
realtime and optional same-frame playback are documented separately in [SYNC_PLAYBACK.md](SYNC_PLAYBACK.md).

Worker slots are supervisors, not preloaded models. A slot reserves only a camera
with a streaming capture, a new frame ID and a fresh decoded frame (default two
seconds). Loading a model does not retain that frame: the latest eligible frame is
read again after loading. Idle ready slots are reused before another model is
loaded. `VIDEO_ANALYSIS_WORKER_IDLE_SECONDS=60` delays retirement, so brief source
outages do not repeatedly load weights. The maximum remains four simultaneous
camera/task jobs; subscriber count never sets model count. Health distinguishes
`worker_count` (capacity) from `running_workers` (actual child processes).

Capture stays lightweight and reconnects independently, including when every
model is dormant. `waiting_frame` means RTSP opened but no decoded frame arrived;
it does not count as streaming. `VIDEO_ANALYSIS_FRAME_FRESH_SECONDS=2` bounds frame
age independently of result lifetime. A model loading/timeout/error is attributed
to its reserved camera, never broadcast as a model failure to offline cameras.
RTSP connect/read failures and codec loss belong to capture, not inference.
The browser displays video progress, capture state and analysis state separately.
Loading, waiting for source, waiting for detection, inference errors and expired
results have separate labels. Expiry uses the browser monotonic clock.

OpenCV's FFmpeg `CAP_PROP_PTS / CAP_PROP_FPS`, when finite and advancing, is exposed
as `media_pts_ms`. It is anchored with the session's minimum `decode_wall - PTS`;
`timestamp_kind=pts_wall_estimate` explicitly denotes an estimate. Unsupported,
negative (including FFmpeg's missing-PTS sentinel), constant or discontinuous PTS
falls back to `decode_wall_clock`. If accumulated drift places the estimate more
than 500 ms behind decode arrival, the anchor is rebuilt and that frame also uses
`decode_wall_clock`. This bounds the estimate's divergence from decode arrival;
it does not establish the age of a frame inside the camera or network. Both include
`decode_ts_ms`; neither represents source-camera capture time. Raw RTSP RTP/RTCP
sender reports are not exposed by this API. In particular, an RTSP PTS and a WHEP
`rtpTimestamp` must not be compared directly: MediaMTX sessions can use different
origins and this implementation has no verified common RTP mapping.

The shared detection socket exchanges `clock_ping {client_ms}` and
`clock_pong {client_ms, server_ms}`. The lowest-RTT sample estimates the server epoch
on the browser monotonic clock, with a 20-second freshness limit. Uncertainty is
at least half the RTT, plus asymmetric transport delay. Without a sample, result
time falls back to receipt minus server frame-to-send duration; this also contains
unknown WebSocket transport delay. This is explicitly `arrival_estimate`.

Each camera retains at most 64 live detection packets, including zero-target frames.
Its renderer observes rVFC `mediaTime`, `receiveTime`, `rtpTimestamp` and optional
`captureTime` for diagnostics. It maps **local** media progression to minimum
browser receive/presentation time, rebuilding the anchor if accumulated drift
exceeds 500 ms; it does not claim `captureTime` and backend PTS are the same clock.
A result is matched to the displayed frame within 1200 ms, covering the default
one-second analysis cadence without periodic blank intervals;
results more than 80 ms in the future are excluded. Old, expired, reordered IDs
and cross-session/epoch messages are rejected. No untracked-person interpolation
or guessed target identities are added. A zero-target result clears its matched
frame's boxes; realtime latest fallback clears on the next video frame. The three-second
result lifetime and fresh-decoded-frame checks still apply when video advances.
When the displayed image freezes, its original annotation snapshot stays with it;
later results, zero targets and expiry do not change that frozen image's boxes.
The next presented frame selects a fresh valid result (including zero targets),
or clears the boxes. This does not refresh a result's validity or carry an expired
box onto a new image. Video disconnect/source changes and visibility resets clear
the snapshot. Each camera retains at most one raw and one delayed-frame annotation
snapshot, with no additional image buffer.

The dashboard uses realtime playback and shows the latest valid result, preserving
live playback and its known annotation lag. The playback-mode selector has been
removed. The internal synchronized renderer remains available for regression
verification: it selects timestamp-matched history packets and copies raw WebRTC frames
into a local bounded Canvas buffer and display them after a target **650 ms**.
This is additional presentation delay, not an end-to-end latency guarantee.
The hard ceiling is **1000 ms**, including held frames. Capture is capped at
12 fps and 640×360 per camera; each buffer is capped at 32 frames and 32 MiB.
If APIs, dimensions or media timing are missing, or bitmap capture/display stops,
the original video remains visible and the mode falls back to realtime. Waiting
for AI never pauses the underlying video or extends the delay. This can lower
synchronized-mode display resolution; realtime retains original resolution.

Rendered, evicted, invalidated and late asynchronous bitmaps are closed. Video
source changes, session/epoch changes and visibility restoration clear playback
buffers. An AI-only session reset can preserve the raw frozen image's annotation
until its next video frame; it never applies that snapshot to the new session's
advancing frames. On foreground restoration the detection connection is re-established
to discard queued old messages. Detection updates and annotation switches do not
recreate the player. The single shared annotation toggle also works in fullscreen.
The compact toolbar shows video and AI status, with capture details in its tooltip.

Canvas data attributes expose actual playback delay, matching delta, time source,
frame/history counts and estimated buffer bytes for reproducible acceptance. A
small matching delta measures **estimated timeline selection**, not actual camera
frame accuracy. Independent RTSP/WebRTC decoder buffering, missing capture/NTP
mapping, sparse inference and network loss remain error sources. Pixel measurements
on a controlled moving test stream are needed to evaluate visual improvement;
they cannot establish precision on unstable production sources.
