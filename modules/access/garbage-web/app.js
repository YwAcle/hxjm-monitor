const $ = id => document.getElementById(id);
const names = ['左上', '中上', '右上', '左中', '中央', '右中', '左下', '中下', '右下'];
let result = null, view = 'live', busy = false, submitting = false, cameraOnline = false, lastJob = null;
let previewUrl = null;
let mode = 'camera', uploadFile = null, uploadUrl = null, serviceOnline = false;
let selectedCamera = 'camera_3';
const results = { upload: null };
const resultKey = () => mode === 'camera' ? selectedCamera : 'upload';
const cameraName = () => `摄像头 ${selectedCamera.split('_')[1]}`;
const formatTime = value => new Date(value).toLocaleString('zh-CN', { hour12: false });
function updateSourceStatus() {
  $('online-dot').classList.toggle('online', serviceOnline && (mode === 'upload' ? !!uploadFile : cameraOnline));
  $('camera-status').textContent = !serviceOnline ? '服务连接中断' : mode === 'upload' ? (uploadFile ? '测试图片已就绪' : '图片检测 · 等待上传') : `${cameraName()} ${cameraOnline ? '已连接' : '未连接'}`;
}
for (let i = 0; i < 9; i++) {
  const region = document.createElement('div');
  region.className = 'region-cell'; region.textContent = names[i];
  $('region-grid').append(region);
  const tile = document.createElement('div');
  tile.className = 'map-cell'; tile.textContent = names[i];
  tile.dataset.id = `r${Math.floor(i / 3) + 1}c${i % 3 + 1}`;
  $('region-map').append(tile);
}

function updateButton() {
  $('detect-button').disabled = busy || submitting || !serviceOnline || (mode === 'camera' ? !cameraOnline : !uploadFile);
  $('detect-button').textContent = busy || submitting ? '检测进行中…' : mode === 'camera' ? '⌕ 截帧并检测' : '⌕ 检测这张图片';
  $('choose-image').disabled = $('choose-empty').disabled = busy || submitting;
  $('detailed-detection').disabled = $('detection-threshold').disabled = busy || submitting;
  updateSourceStatus();
}

function alignOverlay() {
  const image = view === 'live' ? $(mode === 'camera' ? 'camera-image' : 'upload-image') : $('result-image');
  if (image.hidden || !image.naturalWidth) { $('frame-overlay').hidden = true; return; }
  const w = $('viewport').clientWidth, h = $('viewport').clientHeight;
  const scale = Math.min(w / image.naturalWidth, h / image.naturalHeight);
  const iw = image.naturalWidth * scale, ih = image.naturalHeight * scale;
  Object.assign($('frame-overlay').style, { width: `${iw}px`, height: `${ih}px`, left: `${(w - iw) / 2}px`, top: `${(h - ih) / 2}px` });
  $('frame-overlay').hidden = false;
}
new ResizeObserver(alignOverlay).observe($('viewport'));
$('camera-image').addEventListener('load', alignOverlay);
$('result-image').addEventListener('load', alignOverlay);
$('upload-image').addEventListener('load', alignOverlay);

function switchView(next) {
  if (next === 'result' && !result) return;
  view = next;
  for (const name of ['live', 'result']) {
    $(`${name}-tab`).classList.toggle('active', name === next);
    $(`${name}-tab`).setAttribute('aria-pressed', String(name === next));
  }
  $('camera-image').hidden = next !== 'live' || mode !== 'camera' || !cameraOnline;
  $('upload-image').hidden = next !== 'live' || mode !== 'upload' || !uploadFile;
  $('empty-upload').hidden = next !== 'live' || mode !== 'upload' || !!uploadFile;
  $('result-image').hidden = next !== 'result';
  $('boxes').hidden = next !== 'result';
  $('empty-camera').hidden = next !== 'live' || mode !== 'camera' || cameraOnline;
  $('view-label').textContent = next === 'live' ? (mode === 'camera' ? '现场画面' : '上传原图') : '检测截图';
  $('frame-kind').textContent = `${mode === 'camera' ? `CAM 0${selectedCamera.split('_')[1]}` : 'IMAGE'} · ${$('view-label').textContent}`;
  if (next === 'result') $('frame-time').textContent = mode === 'camera' ? `截帧时间 ${formatTime(result.captured_at)}` : `检测图片：${result.file_name || '上传图片'}`;
  else if (mode === 'upload') $('frame-time').textContent = uploadFile ? `${uploadFile.name} · ${(uploadFile.size / 1024 / 1024).toFixed(2)} MB` : '等待选择测试图片';
  else $('frame-time').textContent = `${cameraName()} · 现场画面`;
  alignOverlay();
}
$('live-tab').onclick = () => switchView('live');
$('result-tab').onclick = () => switchView('result');
$('show-grid').onchange = () => $('region-grid').hidden = !$('show-grid').checked;

function clearResult() {
  result = null;
  $('initial-result').hidden = false; $('result-detail').hidden = true;
  $('result-state').textContent = '尚未检测'; $('result-state').className = 'tag';
  for (const id of ['target-count', 'region-count', 'latency']) $(id).firstChild.textContent = '—';
  $('boxes').replaceChildren(); $('category-summary').replaceChildren(); $('snapshot-count').textContent = '';
  $('result-tab').disabled = $('export-button').disabled = true;
  for (const tile of $('region-map').children) tile.classList.remove('occupied');
}

function switchMode(next) {
  mode = next;
  for (const name of ['camera', 'upload']) {
    $(`${name}-mode`).classList.toggle('active', mode === name);
    $(`${name}-mode`).setAttribute('aria-pressed', String(mode === name));
  }
  $('upload-toolbar').hidden = mode !== 'upload';
  $('camera-picker').hidden = mode !== 'camera';
  $('source-title').textContent = mode === 'camera' ? cameraName() : '图片检测';
  $('source-subtitle').textContent = mode === 'camera' ? '固定巡检视角' : '上传样本 · 核对识别结果';
  $('live-tab').textContent = mode === 'camera' ? '现场画面' : '上传原图';
  $('mode-hint').textContent = mode === 'camera' ? `从${cameraName()}截取画面进行识别` : '上传测试图片，对照原图检查漏检和误检';
  $('page-description').textContent = mode === 'camera' ? '观察现场画面，截取一帧，识别散落垃圾及所在区域。' : '上传一张测试图片，对照原图核对垃圾类别、检测框和漏检情况。';
  $('action-title').textContent = mode === 'camera' ? '单帧分析' : '图片分析';
  $('action-description').textContent = mode === 'camera' ? '定位纸屑、瓶罐、包装物、餐盒、烟头等疑似垃圾，检测期间可切换画面。' : '先使用普通检测；小目标漏检时，勾选局部放大复检或降低阈值。';
  $('initial-result').querySelector('p').textContent = mode === 'camera' ? '点击「截帧并检测」后，垃圾类型与位置将在这里显示。' : '选择图片并点击「检测这张图片」，随后对照原图复核。';
  clearResult();
  if (results[resultKey()]) showResult(results[resultKey()]);
  else switchView('live');
  updateButton();
}
for (const button of document.querySelectorAll('.camera-option')) {
  button.onclick = () => {
    if (selectedCamera === button.dataset.camera) return;
    selectedCamera = button.dataset.camera;
    cameraOnline = false;
    $('camera-image').hidden = true;
    $('camera-image').removeAttribute('src');
    if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
    $('camera-image').alt = `${cameraName()}的现场画面`;
    $('camera-error').textContent = `正在获取${cameraName()}画面…`;
    for (const option of document.querySelectorAll('.camera-option')) {
      const selected = option.dataset.camera === selectedCamera;
      option.classList.toggle('active', selected);
      option.setAttribute('aria-pressed', String(selected));
    }
    switchMode('camera');
  };
}
$('camera-mode').onclick = () => switchMode('camera');
$('upload-mode').onclick = () => switchMode('upload');
$('detection-threshold').oninput = () => $('threshold-value').textContent = Number($('detection-threshold').value).toFixed(2);
$('choose-image').onclick = $('choose-empty').onclick = () => $('image-file').click();
$('image-file').onchange = async () => {
  const file = $('image-file').files[0];
  $('image-file').value = '';
  if (!file || busy || submitting) return;
  let nextUrl;
  try {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) throw new Error('请选择不超过 10 MB 的 JPG、PNG 或 WebP 图片。');
    nextUrl = URL.createObjectURL(file);
    const preview = new Image(); preview.src = nextUrl; await preview.decode();
    if (preview.naturalWidth * preview.naturalHeight > 20000000) throw new Error('图片不能超过 2000 万像素。');
    if (uploadUrl) URL.revokeObjectURL(uploadUrl);
    uploadFile = file; uploadUrl = nextUrl; nextUrl = null;
    $('upload-image').src = uploadUrl; $('file-name').textContent = file.name;
    results.upload = null;
    if (mode === 'upload') { clearResult(); switchView('live'); }
    updateButton();
  } catch (error) {
    uploadFile = null;
    if (uploadUrl) { URL.revokeObjectURL(uploadUrl); uploadUrl = null; }
    results.upload = null;
    if (mode === 'upload') { clearResult(); switchView('live'); }
    updateButton();
    $('job-message').textContent = error.message || '无法读取图片，请重新选择。';
    $('file-name').textContent = `图片未载入：${error.message || '格式无效'}`;
  } finally { if (nextUrl) URL.revokeObjectURL(nextUrl); }
};

function showResult(data) {
  result = data;
  $('result-image').src = data.image;
  $('initial-result').hidden = true; $('result-detail').hidden = false;
  $('target-count').firstChild.textContent = data.has_garbage && !data.targets.length ? '—' : data.targets.length;
  const regions = new Set(data.targets.map(t => t.region_id).filter(Boolean));
  $('region-count').firstChild.textContent = data.unlocalized && !regions.size ? '—' : regions.size;
  $('latency').firstChild.textContent = data.elapsed_seconds;
  $('result-state').textContent = data.has_garbage ? '发现疑似垃圾' : '未检出目标';
  $('result-state').className = `tag ${data.has_garbage ? 'warning' : 'success'}`;
  $('scene').textContent = data.scene_description || '模型未提供场景描述';
  $('reason').textContent = data.reason;
  const counts = new Map();
  for (const target of data.targets) counts.set(target.label, (counts.get(target.label) || 0) + 1);
  $('category-summary').replaceChildren(...Array.from(counts, ([label, count]) => {
    const chip = document.createElement('span'); chip.textContent = `${label} × ${count}`; return chip;
  }));
  $('unlocalized').hidden = !data.unlocalized;
  $('target-list').replaceChildren(); $('boxes').replaceChildren();
  data.targets.forEach((target, index) => {
    const item = document.createElement('div'); item.className = 'target-item';
    const number = document.createElement('span'); number.className = 'target-number'; number.textContent = String(index + 1).padStart(2, '0');
    const detail = document.createElement('div'); const label = document.createElement('strong'); label.textContent = target.label;
    const region = document.createElement('span'); region.textContent = target.region_id ? `${target.region_name}区域 · ${target.region_id.toUpperCase()}` : '未定位 · 请复核原图';
    detail.append(label, region);
    const score = document.createElement('span'); score.className = 'score'; score.textContent = target.confidence == null ? '—' : `${Math.round(target.confidence * 100)}%`;
    item.append(number, detail, score); $('target-list').append(item);
    if (!target.bbox) return;
    const [x1, y1, x2, y2] = target.bbox;
    const box = document.createElement('div'); box.className = 'detection-box';
    Object.assign(box.style, { left: `${x1 / 10}%`, top: `${y1 / 10}%`, width: `${(x2 - x1) / 10}%`, height: `${(y2 - y1) / 10}%` });
    const caption = document.createElement('span'); caption.textContent = `${index + 1} · ${target.label}`; box.append(caption); $('boxes').append(box);
  });
  if (!data.has_garbage) $('target-list').textContent = '本帧未识别到散落垃圾，建议结合原图复核。';
  for (const tile of $('region-map').children) tile.classList.toggle('occupied', regions.has(tile.dataset.id));
  $('result-tab').disabled = false; $('export-button').disabled = false;
  $('snapshot-count').textContent = `· ${data.targets.length}`;
  switchView('result');
}

async function request(url, options) {
  const response = await fetch(url, { ...options, signal: AbortSignal.timeout(30000) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}

async function refreshState() {
  const requestedCamera = selectedCamera;
  try {
    const state = await request(`/api/state?camera_id=${requestedCamera}`);
    if (requestedCamera !== selectedCamera) return;
    for (const item of state.cameras || []) {
      const button = document.querySelector(`[data-camera="${item.id}"]`);
      if (button) {
        button.classList.toggle('online', item.online);
        button.querySelector('small').textContent = item.online ? '在线' : '离线';
      }
    }
    if (state.categories) {
      $('category-total').textContent = state.categories.length;
      $('supported-categories').replaceChildren(...state.categories.map(label => {
        const chip = document.createElement('span'); chip.textContent = label; return chip;
      }));
    }
    serviceOnline = true;
    cameraOnline = state.camera.online;
    updateSourceStatus();
    $('camera-error').textContent = state.camera.error || '';
    if (view === 'live' && mode === 'camera') {
      $('empty-camera').hidden = cameraOnline;
      $('camera-image').hidden = !cameraOnline;
      $('frame-time').textContent = cameraOnline ? `最近画面 ${formatTime(state.camera.captured_at)}` : '等待摄像头恢复连接';
      if (!cameraOnline) $('frame-overlay').hidden = true;
    }
    busy = ['loading', 'running'].includes(state.job.state);
    const messages = { idle: '就绪后点击检测；使用 Grounding DINO 直接定位目标。', loading: '正在准备目标检测模型，请稍候…', running: `正在定位垃圾 · ${state.job.detailed ? '基础类别全图及 4 个局部 + 扩展类别全图' : '基础及扩展类别分组检测'} · 最长 120 秒，超时会释放任务`, done: '本次检测完成，可在原图与检测截图之间切换。', error: `检测失败：${state.job.error}` };
    $('job-message').textContent = mode === 'camera' && !cameraOnline && !busy ? state.camera.error : messages[state.job.state];
    if (mode === 'upload' && !busy && state.job.state !== 'error') $('job-message').textContent = uploadFile ? '已选择图片，点击检测。可切换原图与检测截图复核结果。' : '请选择一张测试图片，摄像头断线也可使用图片检测。';
    $('job-message').classList.toggle('error', state.job.state === 'error');
    if (busy) $('job-message').textContent += ` 已等待 ${Math.max(0, Math.floor((Date.now() - Date.parse(state.job.started_at)) / 1000))} 秒`;
    if (state.job.state === 'done' && lastJob !== state.job.id) {
      const data = await request('/api/result');
      if (data.result?.id === state.job.id) {
        const source = data.result.source || 'camera';
        const key = source === 'camera' ? (data.result.camera_id || 'camera_3') : 'upload';
        results[key] = data.result;
        if (key === resultKey()) showResult(data.result);
        lastJob = state.job.id;
      }
    }
    updateButton();
  } catch (error) {
    if (requestedCamera !== selectedCamera) return;
    cameraOnline = false; serviceOnline = false; updateButton();
    $('camera-status').textContent = '服务连接中断'; $('online-dot').classList.remove('online');
    $('job-message').textContent = '无法连接检测服务，正在重试…';
    if (view === 'live' && mode === 'camera') { $('camera-image').hidden = true; $('frame-overlay').hidden = true; $('empty-camera').hidden = false; $('camera-error').textContent = '等待服务恢复连接'; }
  } finally { setTimeout(refreshState, 1000); }
}

async function refreshPreview() {
  const requestedCamera = selectedCamera;
  if (view === 'live' && mode === 'camera' && cameraOnline && !document.hidden) {
    try {
      const response = await fetch(`/api/frame.jpg?camera_id=${requestedCamera}&t=${Date.now()}`, { signal: AbortSignal.timeout(8000) });
      if (response.ok) {
        const blob = await response.blob();
        if (requestedCamera !== selectedCamera || mode !== 'camera') {
          setTimeout(refreshPreview, 0); return;
        }
        const next = URL.createObjectURL(blob);
        $('camera-image').src = next;
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = next;
      }
    } catch { /* The status poll owns the visible connection error. */ }
  }
  setTimeout(refreshPreview, 700);
}
$('detect-button').onclick = async () => {
  submitting = true; updateButton();
  try {
    if (mode === 'upload') {
      if (!uploadFile) throw new Error('请先选择测试图片。');
      await request('/api/detect-image', { method: 'POST', headers: { 'Content-Type': uploadFile.type, 'X-File-Name': encodeURIComponent(uploadFile.name), 'X-Detection-Detail': $('detailed-detection').checked ? '1' : '0', 'X-Detection-Threshold': $('detection-threshold').value }, body: uploadFile });
    } else await request('/api/detect', { method: 'POST', headers: { 'X-Camera-Id': selectedCamera } });
    busy = true; $('job-message').textContent = '图片已提交，准备分析…';
  }
  catch (error) { $('job-message').textContent = error.message; }
  finally { submitting = false; updateButton(); }
};
$('export-button').onclick = () => {
  if (!result) return;
  const { image, ...payload } = result;
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = `${result.source === 'upload' ? 'upload' : (result.camera_id || selectedCamera)}_${result.id}.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
setInterval(() => $('clock').textContent = formatTime(Date.now()), 1000);
refreshState(); refreshPreview();
