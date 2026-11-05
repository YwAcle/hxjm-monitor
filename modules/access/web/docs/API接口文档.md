# 📋 慧心极目·火眼金睛视频监控平台 - 后端接口文档

**文档版本：** v1.0  
**更新日期：** 2025-01-03

---

## 一、接口总览

| 序号 | 功能模块 | 接口类型 | 接口地址 | 说明 |
|:---:|---------|:-------:|---------|------|
| 1 | 接入设备统计 | HTTP GET | `/api/device/stats` | 获取设备接入数量 |
| 2 | 告警综合数据 | WebSocket | `ws://xxx/ws/alarm` | AI分析次数 + 异常统计 + 实时告警 |
| 3 | 行人身份认证 | WebSocket | `ws://xxx/ws/pedestrian` | AI分析次数 + 人流量 + 身份识别记录 |
| 4 | 大模型对话 | HTTP POST | `/chat` | 智能问答（已有） |
| 5 | 视频流 | WebRTC | WHEP协议 | 实时视频（已有） |

---

## 二、详细接口定义

---

### 1️⃣ 接入设备统计（HTTP GET）

**接口地址：** `GET /api/device/stats`

**功能描述：** 获取平台接入的设备数量统计

**请求参数：** 无

**响应示例：**

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "device_count": 23
  }
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|-----|------|-----|
| device_count | number | 接入设备总数 |

**调用频率：** 页面加载时调用一次，或每5分钟轮询一次

---

### 2️⃣ 告警综合数据（WebSocket）⭐ 重点接口

**接口地址：** `ws://your-server/ws/alarm`

**功能描述：** 统一推送以下三类数据：
- **AI分析次数**（平台概览中的"AI分析"）
- **异常事件统计**（圆环图数据 + 异常检测次数）
- **实时告警列表**（底部告警卡片）

#### 2.1 整体流程图

```
┌─────────┐                                              ┌─────────┐
│  前端   │                                              │  后端   │
└────┬────┘                                              └────┬────┘
     │                                                        │
     │  ══════════ 1. 建立连接 ════════════════════════>      │
     │           ws://192.168.96.201:8001/ws/alarm           │
     │                                                        │
     │  <═══════════ 2. 连接成功 ════════════════════════     │
     │                  (WebSocket 握手完成)                  │
     │                                                        │
     │  <──────────── 3. 推送初始数据 ───────────────────     │
     │                  { type: "init", data: {...} }        │
     │                                                        │
     │  ─────────────────────────────────────────────────     │
     │  │                 正常运行阶段                    │    │
     │  ─────────────────────────────────────────────────     │
     │                                                        │
     │  <──────────── 4. 推送新告警 ─────────────────────     │
     │                  { type: "new_alarm", data: {...} }   │
     │                  (有新告警时才推送)                     │
     │                                                        │
     │  ──────────── 5. 心跳请求 ────────────────────────>    │
     │                  { type: "ping" }                      │
     │                  (每30秒一次)                          │
     │                                                        │
     │  <──────────── 6. 心跳响应 ───────────────────────     │
     │                  { type: "pong" }                      │
     │                                                        │
     │  <──────────── 7. 继续推送新告警... ─────────────      │
     │                                                        │
     │  ═══════════ 8. 连接断开 ═════════════════════════     │
     │              (网络问题/服务器重启等)                    │
     │                                                        │
     │  ══════════ 9. 自动重连 ══════════════════════════>    │
     │              (3秒后重试，指数退避)                      │
     │                                                        │
```

#### 2.2 连接成功后初始化推送（init）

**发送时机：** WebSocket 连接建立后，后端**立即**发送

**服务端 → 客户端：**

```json
{
  "type": "init",
  "data": {
    "ai_count": 1500,
    "anomaly": {
      "total": 105,
      "items": [
        { "type": "fight", "count": 30 },
        { "type": "fire", "count": 25 },
        { "type": "fall", "count": 28 },
        { "type": "stranger", "count": 22 }
      ]
    },
    "recent_alarms": [//最新5条
      {
        "id": "alarm_001",
        "alarm_level": "warning",
        "event_type_key": "fight",
        "camera_id": "001",
        "thumbnail": "/alarms/2023-02-20/alarm_001.jpg",
        "record_url": "http://192.168.96.201:8001/alarm/001",
        "timestamp": "2023-02-20 08:47:51"
      },
      {
        "id": "alarm_002",
        "alarm_level": "error",
        "event_type_key": "fire",
        "camera_id": "002",
        "thumbnail": "/alarms/2023-02-20/alarm_002.jpg",
        "record_url": "http://192.168.96.201:8001/alarm/002",
        "timestamp": "2023-02-20 08:47:51"
      }
    ]
  }
}
```

**init 的作用：**
- 页面刚加载时，立即显示当前数据
- 用户刷新页面后，立即恢复显示
- 如果没有 init，页面会空白，需要等待第一次告警才有数据

#### 2.3 新告警推送（new_alarm）

**发送时机：** AI 检测到新的异常事件时

**服务端 → 客户端：**

```json
{
  "type": "new_alarm",
  "data": {
    "ai_count": 1501,
    "alarm": {
      "id": "alarm_003",
      "alarm_level": "warning",
      "event_type_key": "fall",
      "camera_id": "003",
      "thumbnail": "/alarms/2025-01-03/alarm_003.jpg",
      "record_url": "http://192.168.96.201:8001/alarm/003",
      "timestamp": "2025-01-03 10:30:00"
    },
    "anomaly_update": {
      "total": 106,
      "type": "fall",
      "count": 29
    }
  }
}
```

**前端收到后会：**
1. 更新 AI 分析次数：1500 → 1501
2. 更新圆环图总数：105 → 106
3. 更新对应类型计数：fall 28 → 29
4. 在告警列表顶部新增一条

#### 2.4 心跳机制

**客户端 → 服务端：**（每30秒）
```json
{ "type": "ping" }
```

**服务端 → 客户端：**
```json
{ "type": "pong" }
```

#### 2.5 AI分析次数说明

`ai_count` 是多个 AI 功能的汇总统计，包括：

| 来源 | 说明 | 触发时机 |
|-----|------|---------|
| 异常检测 | 检测到打架/摔倒/火灾/陌生人 | 每次检测到异常 +1 |
| 行人身份认证 | 识别到人员身份 | 每次识别成功 +1 |
| 大模型对话 | 用户向大模型提问 | 每次问答 +1 |

**更新方式：**
- 告警 WebSocket 推送 `new_alarm` 时更新（异常检测）
- 行人 WebSocket 推送 `new_identity` 时更新（身份识别）
- 大模型 `/chat` 接口调用时更新（大模型对话）

#### 2.6 字段说明

| 字段 | 类型 | 说明 |
|-----|------|-----|
| ai_count | number | AI分析总次数（异常检测 + 身份识别 + 大模型对话的总和） |
| anomaly.total | number | 异常事件总数（圆环图中心数字） |
| anomaly.items | array | 各类事件统计列表 |
| anomaly.items[].type | string | 事件类型：fight / fire / fall / stranger |
| anomaly.items[].count | number | 该类型事件次数 |
| recent_alarms | array | 最近告警列表（**返回最新5条**） |
| alarm.id | string | 告警唯一ID |
| alarm.alarm_level | string | 告警级别：error(火灾) / warning(打架/摔倒) / info(陌生人) |
| alarm.event_type_key | string | 事件类型标识 |
| alarm.camera_id | string | 摄像头ID |
| alarm.thumbnail | string | 告警截图URL |
| alarm.record_url | string | 告警录像URL |
| alarm.timestamp | string | 告警时间，格式：YYYY-MM-DD HH:mm:ss |

#### 2.7 事件类型对照表

| type 值 | 中文名称 | alarm_level | 圆环图颜色 |
|--------|---------|-------------|-----------|
| fight | 打架监测 | warning | #3EA1FA（蓝色） |
| fire | 烟雾/火灾 | error | #00D4FF（青色） |
| fall | 摔倒监测 | warning | #F5A623（黄色） |
| stranger | 陌生人预警 | info | #E74C3C（红色） |

---

### 3️⃣ 行人身份认证（WebSocket）

**接口地址：** `ws://your-server/ws/pedestrian`

**功能描述：** 统一推送以下数据：
- **今日人流量**（折线图数据，最近8小时）
- **行人身份信息**（识别记录列表，每天最新20条）

#### 3.1 数据规则说明

注意 ： 保证数据一定是 10分钟的倍数
| 数据项 | 规则 |
|-------|------|
| 今日人流量 | **每10分钟记录一次**，显示**最近8小时**的数据（共48个点）。如果当前时间不满8小时（如凌晨2点），则从 00:00 开始从左往右记录 |
| 行人身份信息 | 每天刷新，显示**当天最新20条**识别记录 |

**人流量时间范围示例：**
- 当前时间 15:00 → 显示 07:00 - 15:00 的数据（8小时 × 6个点/小时 = 48个点）
- 当前时间 03:00 → 显示 00:00 - 03:00 的数据（3小时 × 6个点/小时 = 18个点）

**X轴刻度显示：** 只显示整点时间（如 07:00, 08:00, 09:00...），数据点每10分钟一个

**前端渲染：** 使用贝塞尔曲线平滑连接各数据点

#### 3.2 连接成功后初始化推送

**服务端 → 客户端：**

```json
{
  "type": "init",
  "data": {
    "ai_count": 1500,  // AI分析总次数（与告警接口同步）
    "flow": {
      "total_today": 88,
      "start_time": "07:00",  // 数据起始时间
      "end_time": "15:00",    // 数据结束时间
      "data_points": [  // 每10分钟一个点，8小时共48个点
        { "time": "07:00", "count": 2 },
        { "time": "07:10", "count": 1 },
        { "time": "07:20", "count": 3 },
        { "time": "07:30", "count": 2 },
        { "time": "07:40", "count": 4 },
        { "time": "07:50", "count": 3 },
        { "time": "08:00", "count": 5 },
        // ... 省略中间数据 ...
        { "time": "14:50", "count": 8 },
        { "time": "15:00", "count": 6 }
        // 共48个数据点
      ]
    },
    "identities": [  // 今日最新20条识别记录
      {
        "id": 1,
        "name": "张嘉豪",
        "avatar": "/avatars/zhang_jiahao.jpg",
        "age": 20,
        "gender": "男",
        "identity": "学生",
        "camera_id": "001",
        "detected_time": "2025-01-03 15:00:00"
      },
      {
        "id": 2,
        "name": "李昆鸿",
        "avatar": "/avatars/li_kunhong.jpg",
        "age": 21,
        "gender": "女",
        "identity": "教师",
        "camera_id": "003",
        "detected_time": "2025-01-03 14:55:13"
      }
      // ... 最多20条
    ]
  }
}
```

**注意：** `data_points` 数组包含48个元素（8小时 × 每小时6个点），每个元素的 `count` 表示该10分钟时间段内的人流量

#### 3.3 新识别人员推送

**服务端 → 客户端：**（识别到新人员时）

```json
{
  "type": "new_identity",
  "data": {
    "ai_count": 1501,  // AI分析总次数 +1（身份识别）
    "identity": {
      "id": 21,
      "name": "王小明",
      "avatar": "/avatars/wang_xiaoming.jpg",
      "age": 25,
      "gender": "男",
      "identity": "访客",      
      "camera_id": "002",
      "detected_time": "2025-01-03 15:05:00"
    },
    "flow_update": {
      "total_today": 89,
      "time": "15:10",  // 当前10分钟时间点
      "count": 3        // 该10分钟内的人流量（累加后的值）
    }
  }
}
```

**前端收到后会：**
1. 更新 AI 分析次数：1500 → 1501
2. 更新今日总人流量：88 → 89
3. 更新当前10分钟的人流量数据点（如果是新的时间点则新增，否则更新现有点）
4. 如果超过8小时范围，移除最左侧的数据点
5. 在身份列表顶部新增一条（如超过20条，移除最早的记录）

#### 3.4 字段说明

| 字段 | 类型 | 说明 |
|-----|------|-----|
| ai_count | number | AI分析总次数（与告警接口同步，身份识别时 +1） |
| flow.total_today | number | 今日总人流量 |
| flow.start_time | string | 数据起始时间，格式：HH:mm |
| flow.end_time | string | 数据结束时间，格式：HH:mm |
| flow.data_points | array | 人流量时间序列（**每10分钟一个点，最近8小时共48个点**） |
| flow.data_points[].time | string | 时间点，格式：HH:mm |
| flow.data_points[].count | number | **该10分钟内**的人流量（不是累计） |
| identities | array | 已识别人员列表（**今日最新20条**） |
| identity.id | number | 记录ID |
| identity.name | string | 人员姓名 |
| identity.avatar | string | 头像图片URL |
| identity.age | number | 年龄 |
| identity.gender | string | 性别：男 / 女 |
| identity.identity | string | 身份：学生 / 教师 / 员工 / 访客 |
| identity.camera_id | string | 识别该人员的摄像头ID |
| identity.detected_time | string | 识别时间 |

---

### 4️⃣ 大模型对话（HTTP POST）

**接口地址：** `POST http://192.168.96.201:8001/chat`

**功能描述：** 与火眼金睛大模型进行智能问答

**注意：** 每次调用此接口，后端需将 `ai_count` +1，并通过告警 WebSocket 推送更新

**请求头：**
```
Content-Type: application/json
```

**请求体：**

```json
{
  "prompt": "zjh前天早上干了什么",
  "person_name": "zjh",
  "top_k": 10
}
```

**请求参数说明：**

| 字段 | 类型 | 必填 | 说明 |
|-----|------|:---:|-----|
| prompt | string | ✅ | 用户输入的问题 |
| person_name | string | ❌ | 查询的人员名称 |
| top_k | number | ❌ | 返回结果数量，默认10 |

**响应示例：**

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "answer": "根据监控记录分析，zjh在前天早上8:30左右出现在A栋1楼大厅...",
    "summary": "zjh前天早上主要活动区域为A栋和B栋，共被识别5次",
    "frequency": {
      "camera_001": 2,
      "camera_002": 1,
      "camera_003": 2,
      "camera_004": 0
    },
    "keyframes": [
      {
        "camera_id": "001",
        "camera_name": "摄像头001",
        "timestamp": "2025-01-01 08:30:15",
        "thumbnail": "/frames/2025-01-01/zjh_001_083015.jpg"
      }
    ]
  }
}
```

---

### 5️⃣ 视频流（WebRTC WHEP）

**接口地址：** `POST http://192.168.108.238:8889/live/{stream_id}/whep`

**功能描述：** 获取实时视频流（已实现）

**stream_id 示例：**
- `camera_1_reid`
- `camera_2_reid`
- `camera_3_reid`
- `camera_4_reid`

---

## 三、WebSocket 通用规范

### 3.1 消息类型（type 字段）

| type | 方向 | 说明 |
|------|------|-----|
| init | 服务端→客户端 | 连接成功后推送初始数据 |
| new_alarm | 服务端→客户端 | 新告警推送 |
| new_identity | 服务端→客户端 | 新识别人员推送 |
| ping | 客户端→服务端 | 心跳请求 |
| pong | 服务端→客户端 | 心跳响应 |
| error | 服务端→客户端 | 错误信息 |

### 3.2 心跳机制

- 客户端每 **30秒** 发送一次 `ping`
- 服务端收到后立即响应 `pong`
- 若 **60秒** 内未收到心跳，服务端可主动断开连接

### 3.3 AI分析次数同步机制

`ai_count` 需要在多个接口之间保持同步：

```
┌────────────────────────────────────────────────────────────────┐
│                     ai_count 更新来源                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐      │
│  │  异常检测   │     │  身份识别   │     │  大模型对话  │      │
│  │  (告警WS)   │     │  (行人WS)   │     │  (HTTP)     │      │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘      │
│         │                   │                   │              │
│         ▼                   ▼                   ▼              │
│  ┌──────────────────────────────────────────────────────┐     │
│  │              后端 ai_count 统一计数器                │     │
│  └──────────────────────────────────────────────────────┘     │
│         │                   │                                  │
│         ▼                   ▼                                  │
│  ┌─────────────┐     ┌─────────────┐                          │
│  │  告警 WS    │     │  行人 WS    │                          │
│  │  推送更新   │     │  推送更新   │                          │
│  └─────────────┘     └─────────────┘                          │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**同步规则：**
- 任何一个来源更新 `ai_count`，都需要通过**两个 WebSocket** 同时推送
- 或者前端订阅告警 WebSocket 作为 `ai_count` 的唯一来源

### 3.4 重连机制

- 首次重连：3秒后
- 后续重连：指数退避（3s → 6s → 12s → 24s），最大30秒

### 3.5 错误消息格式

```json
{
  "type": "error",
  "code": 500,
  "message": "服务器内部错误"
}
```

---

## 四、前端参考实现

### 4.1 告警 WebSocket Hook

```javascript
import { useState, useEffect, useRef, useCallback } from 'react';

const useAlarmWebSocket = () => {
  const [aiCount, setAiCount] = useState(0);
  const [anomaly, setAnomaly] = useState({ total: 0, items: [] });
  const [recentAlarms, setRecentAlarms] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  
  const wsRef = useRef(null);
  const heartbeatRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttempts = useRef(0);

  // 连接函数
  const connect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    console.log('🔌 正在连接 WebSocket...');
    const ws = new WebSocket('ws://192.168.96.201:8001/ws/alarm');
    wsRef.current = ws;

    // 连接成功
    ws.onopen = () => {
      console.log('✅ WebSocket 已连接');
      setIsConnected(true);
      reconnectAttempts.current = 0;
      
      // 启动心跳
      heartbeatRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);
    };

    // 收到消息
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      switch (msg.type) {
        case 'init':
          setAiCount(msg.data.ai_count);
          setAnomaly(msg.data.anomaly);
          setRecentAlarms(msg.data.recent_alarms);
          break;

        case 'new_alarm':
          setAiCount(msg.data.ai_count);
          setAnomaly(prev => ({
            total: msg.data.anomaly_update.total,
            items: prev.items.map(item =>
              item.type === msg.data.anomaly_update.type
                ? { ...item, count: msg.data.anomaly_update.count }
                : item
            )
          }));
          setRecentAlarms(prev => [msg.data.alarm, ...prev].slice(0, 5));
          break;

        case 'pong':
          break;
      }
    };

    // 连接关闭
    ws.onclose = () => {
      console.log('❌ WebSocket 断开');
      setIsConnected(false);
      
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current);
        heartbeatRef.current = null;
      }
      
      reconnect();
    };

    ws.onerror = (error) => {
      console.error('⚠️ WebSocket 错误:', error);
    };
  }, []);

  // 重连函数
  const reconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }

    // 指数退避：3s → 6s → 12s → 24s，最大30s
    const delay = Math.min(3000 * Math.pow(2, reconnectAttempts.current), 30000);
    reconnectAttempts.current += 1;

    console.log(`🔄 ${delay / 1000}秒后尝试第${reconnectAttempts.current}次重连...`);

    reconnectTimeoutRef.current = setTimeout(() => {
      connect();
    }, delay);
  }, [connect]);

  // 手动重连
  const manualReconnect = useCallback(() => {
    reconnectAttempts.current = 0;
    connect();
  }, [connect]);

  useEffect(() => {
    connect();

    return () => {
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { 
    aiCount, 
    anomaly, 
    recentAlarms, 
    isConnected,
    reconnect: manualReconnect
  };
};

export default useAlarmWebSocket;
```

---

## 五、后端参考实现（Python/FastAPI）

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio
import json

app = FastAPI()

# 存储所有连接的客户端
connected_clients = set()

# 当前数据状态
current_state = {
    "ai_count": 1500,
    "anomaly": {
        "total": 105,
        "items": [
            {"type": "fight", "count": 30},
            {"type": "fire", "count": 25},
            {"type": "fall", "count": 28},
            {"type": "stranger", "count": 22}
        ]
    },
    "recent_alarms": []
}

@app.websocket("/ws/alarm")
async def alarm_websocket(websocket: WebSocket):
    # 接受连接
    await websocket.accept()
    connected_clients.add(websocket)
    print(f"✅ 新客户端连接，当前连接数: {len(connected_clients)}")
    
    try:
        # 发送初始数据
        await websocket.send_json({
            "type": "init",
            "data": current_state
        })
        
        # 持续监听客户端消息
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            # 处理心跳
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        print(f"❌ 客户端断开，当前连接数: {len(connected_clients)}")


# 推送新告警（当AI检测到异常时调用）
async def broadcast_new_alarm(alarm_data: dict):
    global current_state
    
    # 更新状态
    current_state["ai_count"] += 1
    current_state["anomaly"]["total"] += 1
    
    for item in current_state["anomaly"]["items"]:
        if item["type"] == alarm_data["event_type_key"]:
            item["count"] += 1
            break
    
    current_state["recent_alarms"].insert(0, alarm_data)
    current_state["recent_alarms"] = current_state["recent_alarms"][:5]
    
    # 构造推送消息
    message = {
        "type": "new_alarm",
        "data": {
            "ai_count": current_state["ai_count"],
            "alarm": alarm_data,
            "anomaly_update": {
                "total": current_state["anomaly"]["total"],
                "type": alarm_data["event_type_key"],
                "count": next(
                    item["count"] for item in current_state["anomaly"]["items"]
                    if item["type"] == alarm_data["event_type_key"]
                )
            }
        }
    }
    
    # 广播给所有客户端
    for client in connected_clients:
        try:
            await client.send_json(message)
        except:
            pass
```

---

## 六、注意事项

1. **跨域配置**：所有接口需配置 CORS，允许前端域名访问

2. **WebSocket 代理**：Nginx 需配置 WebSocket 代理
   ```nginx
   location /ws/ {
       proxy_pass http://backend;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
   }
   ```

3. **图片资源**：thumbnail、avatar 等 URL 需确保前端可直接访问

4. **时间格式统一**：所有时间字段使用 `YYYY-MM-DD HH:mm:ss` 格式

5. **性能考虑**：
   - WebSocket 推送频率不宜过高
   - 告警列表只保留最新 5 条
   - 人员列表建议分页或限制数量

---

## 七、联系方式

如有疑问，请联系前端开发人员。

