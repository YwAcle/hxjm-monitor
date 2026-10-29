// Wire-format limits mirror video_analysis/config.py; timing is browser-local.
export const SYNC_FRAME_WIDTH = 1280;
export const SYNC_FRAME_HEIGHT = 720;
export const SYNC_MAX_BASE64_LENGTH = 2796204; // ceil(2 MiB / 3) * 4
// Mark a stalled exact image; retain the displayed image and its own boxes.
export const SYNC_STALL_MS = 500;
// Live video advances independently; stale boxes must not follow it indefinitely.
export const REALTIME_MAX_RESULT_AGE_MS = 1000;
