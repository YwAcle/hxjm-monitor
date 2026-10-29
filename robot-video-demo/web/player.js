const $ = id => document.getElementById(id);
const players = [];
const events = [];
const sourceNames = {simulated:'模拟视频 · 非实拍',m20:'M20 WebSocket 摄像头',rtsp:'RTSP 网络摄像头',publisher:'等待外部采集程序发布',disabled:'此路已禁用'};

function log(name, text) {
  events.unshift({time:new Date().toLocaleTimeString('zh-CN',{hour12:false}),text:`${name} · ${text}`});
  events.splice(20);
  $('logs').replaceChildren(...events.map(event => {
    const div=document.createElement('div'), time=document.createElement('time'), span=document.createElement('span');
    time.textContent=event.time;span.textContent=event.text;div.append(time,span);return div;
  }));
}
function summary() { $('online-count').textContent=`${players.filter(p=>p.online).length} / ${players.length}`; }

function iceComplete(pc, signal) {
  if (pc.iceGatheringState==='complete') return Promise.resolve();
  return new Promise((resolve,reject) => {
    const finish=error=>{clearTimeout(timer);pc.removeEventListener('icegatheringstatechange',check);signal.removeEventListener('abort',abort);error?reject(error):resolve();};
    const check=()=>{if(pc.iceGatheringState==='complete')finish();};
    const abort=()=>finish(new DOMException('Connection replaced','AbortError'));
    const timer=setTimeout(()=>finish(new Error('ICE 收集超时')),10000);
    pc.addEventListener('icegatheringstatechange',check);signal.addEventListener('abort',abort,{once:true});
    if(signal.aborted)abort();else check();
  });
}

class CameraPlayer {
  constructor(config) {
    this.config=config;this.active=null;this.enabled=config.enabled;this.online=false;this.previous=null;this.generation=0;this.lastFrameAt=0;this.retryTimer=null;
    this.root=$('camera-template').content.firstElementChild.cloneNode(true);
    this.root.id=config.id;this.root.dataset.source=config.source;
    this.el=role=>this.root.querySelector(`[data-role="${role}"]`);
    this.el('channel').textContent=`CHANNEL ${config.id.slice(-1).padStart(3,'0')}`;
    this.el('name').textContent=config.name;
    this.el('source-tag').textContent=config.source==='simulated'?'SIMULATED / 非实拍':config.id.toUpperCase();
    this.el('source-label').textContent=sourceNames[config.source];
    this.el('endpoint').textContent=config.whep_url;
    this.el('hint').textContent=config.source==='publisher'?'此通道等待独立采集程序发布视频，D435/D455 不会因填写名称而自动连接。':config.source==='simulated'?'独立编码的动态测试画面，色相和白框位置区分通道；不是实物摄像头。':'视频地址在服务器 cameras.json 配置；网页不接收上游账号密码。';
    this.el('reconnect').onclick=()=>this.start();
    this.el('disconnect').onclick=()=>this.stop();
    this.el('fullscreen').onclick=()=>this.el('stage').requestFullscreen().catch(()=>log(config.name,'浏览器不支持全屏'));
    for(const role of ['reconnect','disconnect'])this.el(role).disabled=!config.enabled;
    $('cameras').append(this.root);
    if(config.enabled)void this.connect();else this.indicator('已禁用',false,'修改摄像头配置并重启服务可启用此路。');
  }
  indicator(text, online=false, detail='') {
    this.online=online;this.el('state').textContent=text;this.el('state').className='badge '+(online?'green':'');
    this.el('stage').classList.toggle('playing',online);this.el('overlay-title').textContent=text;
    if(detail)this.el('overlay-detail').textContent=detail;
    summary();
  }
  dispose(session) {
    if(!session)return;
    session.controller.abort();session.pc.close();
    if(session.resource&&!session.deleted){session.deleted=true;void fetch(session.resource,{method:'DELETE',keepalive:true}).catch(()=>{});}
    if(this.el('video').srcObject===session.stream)this.el('video').srcObject=null;
  }
  resetMetrics() {
    this.previous=null;
    for(const role of ['fps','size','bitrate'])this.el(role).textContent='—';
    this.el('frames').textContent='0';this.el('frame-info').textContent='尚未收到解码帧';
  }
  schedule(reason) {
    if(!this.enabled)return;
    clearTimeout(this.retryTimer);this.indicator('等待视频 / 准备重连',false,reason);
    this.retryTimer=setTimeout(()=>void this.connect(),3000);
  }
  start() { if(this.config.enabled){this.enabled=true;void this.connect();} }
  stop() {
    this.enabled=false;this.generation++;clearTimeout(this.retryTimer);
    const old=this.active;this.active=null;this.dispose(old);this.resetMetrics();
    this.indicator('已停止播放',false,'仅停止此页面的这一路播放，其他通道继续运行。');log(this.config.name,'停止播放');
  }
  async connect() {
    if(!this.enabled)return;
    const generation=++this.generation;clearTimeout(this.retryTimer);
    const old=this.active;this.active=null;this.dispose(old);this.resetMetrics();this.lastFrameAt=performance.now();
    const pc=new RTCPeerConnection({iceServers:[]});
    const session={pc,controller:new AbortController(),resource:null,stream:null,deleted:false};this.active=session;
    const current=()=>this.active===session&&this.enabled&&this.generation===generation;
    this.indicator('正在连接视频',false,'正在建立连接，需等待实际解码帧。');log(this.config.name,'建立 WHEP 连接');
    const timeout=setTimeout(()=>session.controller.abort(),20000);
    try {
      pc.addTransceiver('video',{direction:'recvonly'});
      pc.ontrack=event=>{if(!current())return;session.stream=event.streams[0]??new MediaStream([event.track]);this.el('video').srcObject=session.stream;void this.el('video').play().catch(()=>{if(current())log(this.config.name,'请点击连接允许播放');});};
      pc.onconnectionstatechange=()=>{if(current()&&['failed','closed'].includes(pc.connectionState)){log(this.config.name,'媒体连接中断');this.schedule('检查此路源、ICE 地址及 UDP 媒体端口。');}};
      await pc.setLocalDescription(await pc.createOffer());await iceComplete(pc,session.controller.signal);
      if(!current())return;
      const response=await fetch(this.config.whep_url,{method:'POST',headers:{'Content-Type':'application/sdp'},body:pc.localDescription.sdp,signal:session.controller.signal});
      const location=response.headers.get('Location');if(location)session.resource=new URL(location,this.config.whep_url).href;
      if(!current()){this.dispose(session);return;}
      if(!response.ok)throw new Error(`WHEP HTTP ${response.status}`);
      const answer=await response.text();if(!current()){this.dispose(session);return;}
      await pc.setRemoteDescription({type:'answer',sdp:answer});
      if(current())log(this.config.name,'协商完成，等待视频帧');
    } catch(error) {
      if(current()) {
        log(this.config.name,error.name==='AbortError'?'连接超时':error.message);
        this.active=null;this.dispose(session);
        this.schedule(this.config.source==='publisher'?'等待采集程序向此路发布视频。':'请检查此路视频源和 MediaMTX 日志。');
      }
    } finally {clearTimeout(timeout);}
  }
  async stats() {
    const session=this.active;if(!session||!this.enabled)return;
    try {
      const report=await session.pc.getStats();if(this.active!==session)return;
      let inbound;report.forEach(r=>{if(r.type==='inbound-rtp'&&(r.kind==='video'||r.mediaType==='video')&&!r.isRemote)inbound=r;});
      const now=performance.now();
      if(inbound) {
        const frames=inbound.framesDecoded??0,bytes=inbound.bytesReceived??0;
        if(this.previous===null?frames>0:frames>this.previous.frames)this.lastFrameAt=now;
        const delta=this.previous?(inbound.timestamp-this.previous.time)/1000:0;
        this.el('frames').textContent=String(frames);
        this.el('size').textContent=inbound.frameWidth?`${inbound.frameWidth} × ${inbound.frameHeight}`:'—';
        this.el('fps').textContent=delta>0?`${Math.max(0,(frames-this.previous.frames)/delta).toFixed(1)} FPS`:'—';
        this.el('bitrate').textContent=delta>0?`${Math.max(0,(bytes-this.previous.bytes)*8/delta/1000).toFixed(0)} kbps`:'—';
        this.previous={frames,bytes,time:inbound.timestamp};
        if(frames>0&&now-this.lastFrameAt<3500){this.indicator('● 视频在线',true);this.el('frame-info').textContent=`实际解码 ${frames} 帧 · ${session.pc.connectionState}`;}
      }
      if(now-this.lastFrameAt>3500)this.indicator('等待新的视频帧',false,'当前没有新解码帧，已隐藏旧画面。');
      if(now-this.lastFrameAt>12000){log(this.config.name,'无新帧，重建此路连接');void this.connect();}
    } catch {/* A replaced/closed connection can reject getStats. */}
  }
}

async function health() {
  try {
    const r=await fetch('/api/health',{signal:AbortSignal.timeout(2500)});if(!r.ok)throw Error();
    const data=await r.json();$('server-state').textContent='后端已连接';$('server-dot').className='ok';
    for(const source of data.sources??[]) {
      const player=players.find(item=>item.config.id===source.id);if(!player)continue;
      const stale=source.age_seconds>8&&source.stage==='forwarding';
      player.el('source-diagnostic').textContent=stale?'近期没有新的接收诊断，等待源恢复。':source.detail;
      player.el('source-diagnostic').dataset.stage=stale?'stale':source.stage;
    }
    $('processes').replaceChildren(...Object.entries(data.processes).map(([key,p])=>{
      const div=document.createElement('div'),name=document.createElement('span'),state=document.createElement('b');
      div.className='process '+(p.running?'ok':'');name.textContent=key;state.textContent=p.running?'运行中':`已退出 (${p.returncode})`;div.append(name,state);return div;
    }));
  } catch {$('server-state').textContent='后端连接中断';$('server-dot').className='';for(const player of players)player.el('source-diagnostic').textContent='后端中断，接收诊断不可用。';}
  setTimeout(health,2000);
}
$('reconnect-all').onclick=()=>players.forEach(player=>player.start());
$('disconnect-all').onclick=()=>players.forEach(player=>player.stop());
window.addEventListener('pagehide',()=>players.forEach(player=>player.stop()));
function updateClock() {
  const now=new Date(),pad=value=>String(value).padStart(2,'0');
  $('clock').textContent=`${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}
updateClock();setInterval(updateClock,1000);
try {
  const response=await fetch('/api/config');if(!response.ok)throw Error('配置读取失败');
  const config=await response.json(),simulated=config.mode==='simulated';
  $('mode').textContent=simulated?'四路模拟 · 非实拍':'四路实物接入模式';$('mode').className='badge '+(simulated?'amber':'green');
  $('banner').textContent=simulated?'模拟模式：四路独立 H.264 测试视频，均经过 WebSocket → RTSP → WebRTC；画面不是机器狗实拍。':'实物模式：前后摄与两路外接相机分别接入。未收到视频的通道显示等待，不会替换成模拟画面。';
  $('banner').classList.toggle('hardware',!simulated);
  for(const camera of config.cameras)players.push(new CameraPlayer(camera));summary();
} catch(error) {$('banner').textContent='无法读取配置，请先启动 Python 服务并通过 HTTP 打开页面。';log('系统',error.message);}
async function statsLoop(){await Promise.allSettled(players.map(player=>player.stats()));setTimeout(statsLoop,1000);}
void statsLoop();void health();
