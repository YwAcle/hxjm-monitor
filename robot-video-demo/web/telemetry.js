const container = document.getElementById('device-states');
const connection = document.getElementById('telemetry-connection');
const cards = new Map();
let snapshot = null;
let received = 0;
let connected = false;

const timeText = value => value ? new Date(value).toLocaleTimeString('zh-CN', {hour12: false}) : '尚未上报';

function buildCard(device) {
  const card = document.createElement('article');
  card.className = 'panel device-card';
  card.id = `device-${device.id}`;
  card.innerHTML = `<div class="title"><h2></h2><span class="badge" data-status></span></div>
    <div class="device-body"><div class="device-current" role="status" aria-live="polite"></div>
    <p class="device-description"></p><ul class="state-options" aria-label="状态列表"></ul>
    <div class="device-meta"><span data-source></span><span data-updated></span></div>
    <details class="state-history"><summary>最近状态变化（历史记录）</summary><ol></ol></details></div>`;
  card.querySelector('h2').textContent = device.name;
  for (const state of device.states) {
    const item = document.createElement('li');
    item.dataset.state = state.code;
    item.textContent = state.label;
    item.title = state.description;
    card.querySelector('.state-options').append(item);
  }
  const target = device.id === 'arm' ? document.getElementById('arm-states') : container;
  target.append(card);
  cards.set(device.id, card);
  return card;
}

function render() {
  const elapsed = (performance.now() - received) / 1000;
  const streamLive = connected && elapsed < 3.5;
  connection.textContent = streamLive ? '状态通道已连接 · 每秒刷新' : '状态通道中断 / 重连中';
  connection.classList.toggle('connected', streamLive);
  if (!snapshot) return;
  let freshCount = 0;
  for (const device of snapshot.devices) {
    const card = cards.get(device.id) || buildCard(device);
    const age = device.age_seconds === null ? null : device.age_seconds + elapsed;
    const fresh = streamLive && age !== null && age < snapshot.stale_after_seconds;
    if (fresh) freshCount++;
    const state = fresh ? device.current_state : null;
    const definition = device.states.find(item => item.code === state);
    const badge = card.querySelector('[data-status]');
    badge.textContent = !streamLive ? '连接中断' : age === null ? '待接入' : !fresh ? '状态过期' : state === 'unknown' ? '已上报 · 未知' : '状态在线';
    badge.className = `badge ${fresh && definition ? 'green' : 'amber'}`;
    const current = card.querySelector('.device-current');
    const nextText = definition ? definition.label : !streamLive ? '状态不可用' : age === null ? '等待设备状态' : !fresh ? '当前状态未知' : '设备上报未知';
    // Avoid re-announcing an unchanged state on each heartbeat.
    if (current.textContent !== nextText) current.textContent = nextText;
    card.querySelector('.device-description').textContent = definition ? definition.description :
      age === null ? '尚未收到该设备状态；不会根据视频在线情况推测设备动作。' :
      `最近上报：${device.reported_label}。${fresh ? '设备未提供可识别状态。' : '仅作历史参考，等待新的有效状态。'}`;
    for (const item of card.querySelectorAll('[data-state]')) {
      const active = !!definition && item.dataset.state === state;
      item.classList.toggle('active', active);
      if (active) item.setAttribute('aria-current', 'true');
      else item.removeAttribute('aria-current');
    }
    card.querySelector('[data-source]').textContent = snapshot.mode === 'simulated' ? '模拟演示 · 非实物状态' : '实物接口 · 以上报为准';
    card.querySelector('[data-updated]').textContent = `后端接收：${timeText(device.received_at)}${age === null ? '' : ` · ${Math.floor(age)} 秒前`}`;
    const history = card.querySelector('.state-history ol');
    const signature = JSON.stringify(device.history);
    if (history.dataset.signature !== signature) {
      history.dataset.signature = signature;
      history.replaceChildren();
      for (const event of device.history) {
        const item = document.createElement('li');
        item.textContent = `${timeText(event.received_at)} · ${event.label}`;
        history.append(item);
      }
      if (!device.history.length) {
        const item = document.createElement('li');
        item.textContent = '暂无状态变化记录';
        history.append(item);
      }
    }
  }
  document.getElementById('state-online-count').textContent = `${freshCount} / ${snapshot.devices.length}`;
}

const stream = new EventSource('/api/telemetry/events');
stream.addEventListener('telemetry', event => {
  try {
    const data = JSON.parse(event.data);
    if (!Array.isArray(data.devices) || !Number.isFinite(data.stale_after_seconds)) throw new Error('状态格式错误');
    snapshot = data;
    received = performance.now();
    connected = true;
    render();
  } catch {
    connected = false;
    render();
  }
});
stream.onerror = () => { connected = false; render(); };
const timer = setInterval(render, 1000);
document.addEventListener('visibilitychange', render);
window.addEventListener('pagehide', () => { clearInterval(timer); stream.close(); });
window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
