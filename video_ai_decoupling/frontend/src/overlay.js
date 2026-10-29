export const DETECTION_TTL_MS = 3000;

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

export function clearOverlay(canvas) {
  const context = canvas.getContext('2d');
  if (context) {
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
  }
  canvas.dataset.drawnBoxes = '0';
  canvas.dataset.frameId = '';
}

export function drawOverlay(canvas, video, packet, enabled, now = performance.now()) {
  const bounds = canvas.getBoundingClientRect();
  const pixelRatio = window.devicePixelRatio || 1;
  const width = Math.round(bounds.width * pixelRatio);
  const height = Math.round(bounds.height * pixelRatio);
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  clearOverlay(canvas);

  if (!enabled || !packet || now - packet.receivedAt >= DETECTION_TTL_MS
      || !video || video.readyState < 2 || video.paused || width <= 0 || height <= 0) {
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

  for (const detection of packet.message.detections) {
    const box = mapBox(detection.bbox, rect);
    const label = `${detection.label} ${Math.round(detection.confidence * 100)}%`;
    const labelWidth = Math.min(context.measureText(label).width + 8, rect.width);
    const labelX = Math.max(rect.x, Math.min(box.x, rect.x + rect.width - labelWidth));
    const labelY = Math.max(rect.y, box.y - 22);
    context.strokeStyle = '#42e3c1';
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
