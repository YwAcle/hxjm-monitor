"""Read-only device observations, independent of the camera transport."""
import asyncio
from datetime import datetime, timezone
import time


DEVICES = {
    "dog": {
        "name": "M20 Pro 机器狗",
        "states": [
            {"code": "lying", "label": "趴", "description": "机器狗处于趴下姿态。"},
            {"code": "standing", "label": "站", "description": "机器狗处于站立姿态。"},
            {"code": "navigating", "label": "导航", "description": "机器狗正在执行导航任务。"},
            {"code": "adjusting", "label": "移动", "description": "扫描到垃圾后，相对于目标垃圾调整最终抓取位置和姿态。"},
        ],
    },
    "arm": {
        "name": "DM-B601 机械臂",
        "states": [
            {"code": "stopped", "label": "停止", "description": "机械臂状态机上报停止；此状态不等同于急停或断电。"},
            {"code": "pre_grasp", "label": "预抓取", "description": "机械臂进入抓取前的准备阶段。"},
            {"code": "grasping", "label": "抓取", "description": "机械臂正在执行抓取动作。"},
            {"code": "holding_return", "label": "保持抓取并回到初始位置等待", "description": "保持抓取，回到初始位置并等待下一步任务；是否已回位须由设备另行确认。"},
            {"code": "pre_place", "label": "预放置", "description": "机械臂进入放置前的准备阶段。"},
            {"code": "placing", "label": "放置", "description": "机械臂正在执行放置动作。"},
        ],
    },
}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class TelemetryStore:
    def __init__(self, mode, clock=time.monotonic, stale_after=5.0):
        self.mode = mode
        self.clock = clock
        self.stale_after = stale_after
        self.latest = {}
        self.history = {key: [] for key in DEVICES}

    def update(self, device, state):
        if device not in DEVICES:
            raise KeyError(device)
        states = {item["code"]: item for item in DEVICES[device]["states"]}
        if state not in states and state != "unknown":
            raise ValueError("该设备不支持此状态码")
        previous = self.latest.get(device)
        now = utc_now()
        label = states[state]["label"] if state in states else "未知"
        self.latest[device] = {"state": state, "label": label, "received_at": now,
                               "tick": self.clock()}
        if previous is None or previous["state"] != state:
            self.history[device].insert(0, {"state": state, "label": label, "received_at": now})
            del self.history[device][6:]

    def snapshot(self):
        now = self.clock()
        devices = []
        for key, definition in DEVICES.items():
            latest = self.latest.get(key)
            age = max(0, now - latest["tick"]) if latest else None
            connection = "waiting" if latest is None else "stale" if age >= self.stale_after else "online"
            devices.append({"id": key, **definition,
                            "connection": connection,
                            "reported_state": latest["state"] if latest else None,
                            "reported_label": latest["label"] if latest else "未知",
                            "current_state": latest["state"] if connection == "online" else None,
                            "received_at": latest["received_at"] if latest else None,
                            "age_seconds": round(age, 3) if age is not None else None,
                            "history": list(self.history[key])})
        return {"mode": self.mode, "server_time": utc_now(),
                "stale_after_seconds": self.stale_after, "devices": devices}


# Demonstration only; not a controller or a physical device state machine.
SIMULATION = [
    ("lying", "stopped"), ("standing", "stopped"),
    ("navigating", "stopped"), ("adjusting", "stopped"),
    ("standing", "pre_grasp"), ("standing", "grasping"),
    ("standing", "holding_return"), ("navigating", "holding_return"),
    ("standing", "pre_place"), ("standing", "placing"),
    ("standing", "stopped"), ("lying", "stopped"),
]


def simulate_step(store, step):
    dog, arm = SIMULATION[step % len(SIMULATION)]
    store.update("dog", dog)
    store.update("arm", arm)


async def simulate(store):
    tick = 0
    while True:
        simulate_step(store, tick // 4)
        await asyncio.sleep(1)
        tick += 1
