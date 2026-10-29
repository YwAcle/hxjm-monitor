const smoothedBoxesByCanvas = new WeakMap();

export function containRect(width, height, sourceWidth, sourceHeight) {
  if ([width, height, sourceWidth, sourceHeight].some(value => !Number.isFinite(value) || value <= 0)) {
    return null;
  }
  const scale = Math.min(width / sourceWidth, height / sourceHeight);
  const fittedWidth = sourceWidth * scale;
  const fittedHeight = sourceHeight * scale;
  return {
    x: (width - fittedWidth) / 2,
    y: (height - fittedHeight) / 2,
    width: fittedWidth,
    height: fittedHeight,
  };
}

export function mapBox(bbox, rect) {
  return {
    x: rect.x + bbox[0] * rect.width,
    y: rect.y + bbox[1] * rect.height,
    width: (bbox[2] - bbox[0]) * rect.width,
    height: (bbox[3] - bbox[1]) * rect.height,
  };
}

function clearCanvas(canvas) {
  const context = canvas.getContext('2d');
  if (context) {
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
  }
}

export function clearOverlay(canvas) {
  clearCanvas(canvas);
  smoothedBoxesByCanvas.delete(canvas);
  canvas.dataset.drawnBoxes = '0';
  canvas.dataset.frameId = '';
}

function smoothDetections(canvas, message) {
  const identity = [message.service_session_id, message.stream_session_id,
    message.session_generation, message.stream_epoch].join(':');
  const previous = smoothedBoxesByCanvas.get(canvas);
  const previousBoxes = previous?.identity === identity ? previous.boxes : new Map();
  const boxes = new Map();
  const detections = message.detections.map(detection => {
    if (!Number.isSafeInteger(detection.track_id)) return detection;
    const old = previousBoxes.get(detection.track_id);
    if (!old) {
      boxes.set(detection.track_id, detection);
      return detection;
    }
    const centerDistance = Math.hypot(
      (old.bbox[0] + old.bbox[2] - detection.bbox[0] - detection.bbox[2]) / 2,
      (old.bbox[1] + old.bbox[3] - detection.bbox[1] - detection.bbox[3]) / 2,
    );
    const alpha = centerDistance > 0.018 ? 0.985 : 0.93;
    const smoothed = { ...detection, bbox: detection.bbox.map((value, index) =>
      old.bbox[index] + (value - old.bbox[index]) * alpha) };
    boxes.set(detection.track_id, smoothed);
    return smoothed;
  });
  smoothedBoxesByCanvas.set(canvas, { identity, boxes });
  return detections;
}

export function drawOverlay(canvas, video, packet, enabled, now = performance.now(), frozen = false) {
  const bounds = canvas.getBoundingClientRect();
  const pixelRatio = window.devicePixelRatio || 1;
  const width = Math.round(bounds.width * pixelRatio);
  const height = Math.round(bounds.height * pixelRatio);
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  clearCanvas(canvas);
  canvas.dataset.drawnBoxes = '0';
  canvas.dataset.frameId = '';

  if (!enabled || !packet || (!frozen && now >= packet.expiresAt)
      || !video || video.readyState < 2 || (video.paused && !frozen) || width <= 0 || height <= 0) {
    smoothedBoxesByCanvas.delete(canvas);
    return 0;
  }
  const videoBounds = video.getBoundingClientRect();
  const fitted = containRect(videoBounds.width, videoBounds.height, video.videoWidth, video.videoHeight);
  if (!fitted) return 0;
  const rect = {
    ...fitted,
    x: fitted.x + videoBounds.left - bounds.left,
    y: fitted.y + videoBounds.top - bounds.top,
  };
  const context = canvas.getContext('2d');
  if (!context) return 0;
  context.setTransform(width / bounds.width, 0, 0, height / bounds.height, 0, 0);
  context.save();
  context.beginPath();
  context.rect(rect.x, rect.y, rect.width, rect.height);
  context.clip();
  context.lineWidth = 2;
  context.font = '600 12px system-ui, sans-serif';
  context.textBaseline = 'top';
  context.setLineDash?.([]);

  const detections = smoothDetections(canvas, packet.message);
  for (const detection of detections) {
    const box = mapBox(detection.bbox, rect);
    const identity = detection.track_id == null ? 'person' : `ID ${detection.track_id}`;
    const label = detection.confidence == null ? identity : `${identity} ${detection.confidence.toFixed(2)}`;
    const labelWidth = Math.min(context.measureText(label).width + 8, rect.width);
    const labelX = Math.max(rect.x, Math.min(box.x, rect.x + rect.width - labelWidth));
    const labelY = Math.max(rect.y, box.y - 22);
    const colors = ['#42e3c1', '#ffcb66', '#7ebaff', '#ff8fab', '#d1a0ff', '#a8e06f'];
    context.strokeStyle = colors[(detection.track_id || 0) % colors.length];
    context.strokeRect(box.x, box.y, box.width, box.height);
    context.fillStyle = 'rgba(7, 25, 35, 0.92)';
    context.fillRect(labelX, labelY, labelWidth, 22);
    context.fillStyle = '#a5ffe9';
    context.fillText(label, labelX + 4, labelY + 3);
  }
  context.restore();
  canvas.dataset.drawnBoxes = String(packet.message.detections.length);
  canvas.dataset.frameId = String(packet.message.frame_id);
  return packet.message.detections.length;
}
