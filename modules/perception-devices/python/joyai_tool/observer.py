"""JoyAI's upstream streaming adapter, with worktree-isolated camera sessions."""
import base64
import json
import re
import uuid
import urllib.error
import urllib.request

from .verdict import VisionReviewer, parse_verdict, VERDICT_RULES, VERDICT_FORMAT


PROMPT = """你是持续观察监控视频的助手，只报告打架和跌倒，不能把交谈、拥抱、弯腰、坐下当成异常。
当前帧是最新时刻，必须结合此前动作判断，不编造不可见过程。
正常或没有值得报告的变化，只输出 </silence>。
明确看见异常时输出 </response> 后跟一行 JSON，遵守下述报告与判定规则。
任务困难、证据不足或无法排除异常时，输出 </response> 简短观察 </delegation> 后跟一行 JSON：
{"kind":"fight或fall或none","question":"需要后台进一步判断的问题与已经观察到的动作"}。
none 表示无法确定异常种类，后台将分别审查打架和跌倒。不要将委托写成已确认异常。
""" + VERDICT_RULES + "\n" + VERDICT_FORMAT


def parse_action(text, confidence=0.7):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("JoyAI 返回空结果")
    text = text.strip()
    if text == "</silence>":
        return {"action": "silence", "candidates": []}
    marker = re.search(r"</?delegation>", text)
    if marker:
        question = text[marker.end():].strip()
        if not question:
            raise ValueError("JoyAI 委托缺少问题")
        # The native model can delegate free text as well as the requested JSON.
        kind = "none"
        if question.startswith("{"):
            value = json.loads(question)
            kind, question = value.get("kind"), value.get("question")
            if kind not in ("fight", "fall", "none") or not isinstance(question, str) or not question.strip():
                raise ValueError("JoyAI 委托格式无效")
        kinds = (kind,) if kind != "none" else ("fight", "fall")
        return {"action": "delegate", "candidates": [
            {"kind": item, "score": 0, "reason": question[:4000], "trigger": "delegation"} for item in kinds]}
    native_response = text.startswith("</response>")
    if native_response:
        text = text[len("</response>"):].strip()
        if text and not text.startswith(("{", "```")):
            # Native spoken responses have no structured verdict; request visual review.
            return {"action": "delegate", "candidates": [
                {"kind": kind, "score": 0, "reason": text[:4000], "trigger": "delegation"}
                for kind in ("fight", "fall")]}
    if text.startswith("```"):
        text = "\n".join(text.splitlines()[1:-1])
    value = json.loads(text)
    kind = value.get("kind")
    if kind == "none" and value.get("decision") == "rejected":
        parse_verdict(text, "fight", confidence)
        return {"action": "silence", "candidates": []}
    if kind not in ("fight", "fall"):
        raise ValueError("JoyAI 异常类型无效")
    verdict = parse_verdict(text, kind, confidence)
    if verdict["decision"] == "rejected":
        return {"action": "silence", "candidates": []}
    candidate = {"kind": kind, "score": verdict["confidence"], "reason": verdict["reason"],
                 "trigger": "delegation" if verdict["decision"] == "uncertain" else "joyai",
                 "verdict": verdict}
    return {"action": "delegate" if verdict["decision"] == "uncertain" else "response",
            "candidates": [candidate]}


class JoyAnalyzer:
    def __init__(self, base_url="", model="jdopensource/JoyAI-VL-Interaction", api_key="", timeout=30, confidence=0.7):
        self.endpoint = VisionReviewer(base_url, model, api_key, timeout, confidence)
        if not self.endpoint.configured:
            raise RuntimeError("JoyAI 未配置，请先部署并设置 JOYAI_OBSERVER_BASE_URL")
        self.models = {kind: {"enabled": True, "reason": "JoyAI 视频观察，困难任务委托 Qwen"}
                       for kind in ("fight", "fall")}
        self.reset()

    def reset(self):
        self.close()
        self.session = "hxjm-" + uuid.uuid4().hex
        self.started = None
        self.turns = 0

    def close(self):
        if getattr(self, "started", None) is None:
            return
        headers = {"Content-Type": "application/json", "x-streaming-session": self.session}
        if self.endpoint.api_key:
            headers["Authorization"] = "Bearer " + self.endpoint.api_key
        request = urllib.request.Request(self.endpoint.base_url + "/streaming/reset", data=b"{}", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=3):
                pass
        except (OSError, urllib.error.URLError):
            pass
        self.started = None

    def analyze(self, frame, stamp):
        import cv2
        # Upstream retains per-turn traces even without saving files; bound their lifetime.
        if self.turns >= 120:
            self.reset()
        ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            raise RuntimeError("JoyAI 输入帧编码失败")
        if self.started is None:
            self.started = stamp
        body = {"model": self.endpoint.model, "stream": False, "temperature": 0, "max_tokens": 512,
                "frame_time_range": f"{max(0, stamp - self.started):.3f} seconds",
                "messages": [{"role": "system", "content": PROMPT},
                             {"role": "user", "content": [
                                 {"type": "text", "text": "持续观察打架和跌倒；困难判断请委托后台。"},
                                 {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," +
                                     base64.b64encode(jpeg.tobytes()).decode("ascii")}}]}]}
        headers = {"Content-Type": "application/json", "x-streaming-session": self.session}
        if self.endpoint.api_key:
            headers["Authorization"] = "Bearer " + self.endpoint.api_key
        request = urllib.request.Request(self.endpoint.base_url + "/chat/completions",
                                         data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.endpoint.timeout) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError("响应过大")
            value = json.loads(raw)
            # Upstream normalization keeps only the first line; raw_content preserves delegation.
            text = value.get("streamingharness", {}).get("raw_content")
            if text is None:
                text = value["choices"][0]["message"]["content"]
            result = parse_action(text, self.endpoint.confidence)
            self.turns += 1
        except urllib.error.HTTPError as exc:
            if exc.code in (502, 503, 504):
                raise RuntimeError(f"JoyAI 接口返回 HTTP {exc.code}：推理上游不可用或超时；请检查 joy_model.log 和系统内存，资源足够后运行 bash scripts/joyai-tool.sh start 恢复观察服务") from None
            raise RuntimeError(f"JoyAI 接口返回 HTTP {exc.code}") from None
        except (OSError, urllib.error.URLError):
            raise RuntimeError("JoyAI 连接失败或请求超时，请检查推理服务") from None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise RuntimeError("JoyAI 返回格式无效，未确认异常") from None
        height, width = frame.shape[:2]
        for candidate in result["candidates"]:
            candidate["box"] = [0, 0, width, height]
        return {"candidates": result["candidates"], "joyAction": result["action"],
                "joyMessage": str(text)[:4000]}, frame
