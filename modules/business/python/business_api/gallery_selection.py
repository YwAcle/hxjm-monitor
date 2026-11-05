"""有时限、有容量限制的截图选择状态；图片不写入聊天历史。"""
from collections import OrderedDict
from threading import RLock
from time import monotonic
import re


class ReIDSelections:
    def __init__(self, gallery, *, ttl_s=300, max_sessions=16, max_chars=32 * 1024 * 1024):
        self.gallery = gallery
        self.ttl_s, self.max_sessions, self.max_chars = ttl_s, max_sessions, max_chars
        self.pending = OrderedDict()
        self.lock = RLock()

    def _prune(self):
        now = monotonic()
        for key in list(self.pending):
            if now - self.pending[key]["created"] >= self.ttl_s:
                del self.pending[key]

    def clear(self, session_id):
        with self.lock:
            return self.pending.pop(session_id, None) is not None

    def remember(self, session_id, image, data):
        if not image or not isinstance(data, dict) or data.get("type") != "pedestrian_selection":
            return
        with self.lock:
            self._prune()
            self.pending.pop(session_id, None)
            if len(image) > self.max_chars:
                raise ValueError("截图超过待选择状态容量限制，请缩小图片")
            while self.pending and (len(self.pending) >= self.max_sessions or
                    sum(len(item["image"]) for item in self.pending.values()) + len(image) > self.max_chars):
                self.pending.popitem(last=False)
            self.pending[session_id] = {"created": monotonic(), "image": image, "data": data}

    def resume(self, session_id, prompt, image=None):
        with self.lock:
            self._prune()
            if image:
                self.pending.pop(session_id, None)
                return None
            pending = self.pending.get(session_id)
            match = re.fullmatch(r"(?:选择|选|第)?\s*([0-9]{1,3}|[一二三四五六七八九十两])\s*(?:号|个|个人)?[。.!！]?", prompt.strip())
            if pending is None:
                if match:
                    return {"type": "pedestrian_selection", "status": "selection_expired", "message": "没有有效的待选择截图，请重新上传截图并发起找人。"}
                return None
            if prompt.strip() in {"取消", "取消选择", "取消找人"}:
                self.pending.pop(session_id)
                return {"type": "pedestrian_selection", "status": "cancelled", "message": "已取消本次截图找人。"}
            if not match:
                return dict(pending["data"], message="请明确回复编号，例如：选择2；也可以回复取消，或上传新图片。")
            number = {"一": "1", "二": "2", "两": "2", "三": "3", "四": "4", "五": "5",
                      "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}.get(match[1], match[1])
            selected = next((c for c in pending["data"]["candidates"] if c["candidate_id"] == number), None)
            if selected is None:
                return dict(pending["data"], message="该编号不在本次候选中，请从显示的编号中选择。")
            # 只使用服务器保存的图片和框，模型或用户不能改写 bbox。
            result = self.gallery.search_selected(pending["image"], selected["bbox"], pending["data"]["top_k"])
            result["source_asset_id"] = pending["data"]["source_asset_id"]
            result["selected_candidate_id"] = selected["candidate_id"]
            self.pending.pop(session_id)
            return result


def selection_text(data):
    if data.get("type") == "pedestrian_search" and data.get("status") == "ok":
        return "找到以下外观相似候选，分数不是身份确认概率：\n" + "\n".join(
            f"{index}. {candidate.get('name', '')}，相似度 {candidate['similarity']:.4f}"
            for index, candidate in enumerate(data["candidates"], 1))
    return data.get("message", "未找到可用的登记候选。")
