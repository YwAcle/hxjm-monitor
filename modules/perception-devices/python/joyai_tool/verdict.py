"""Vision chat adapter: one request per suspicious clip, strict tri-state verdicts."""
import json
import math
import errno
from urllib.parse import urlsplit
import urllib.error
import urllib.request


# Shared by the continual observer and the clip reviewer so neither can bypass the report contract.
VERDICT_RULES = """先客观观察，再核对证据，最后判定，不能为了支持初筛而寻找异常。
初筛类型和委托描述只是假设，不是事实；只使用提供的画面，不能补写未显示的动作或人物意图。
打架：必须明确是真人，并在不同时刻看到针对他人的攻击动作及动作变化，例如挥拳击打、踢打或攻击性推搡；
不要求双方互殴，但单纯靠近、交谈、握手、拥抱、正常工作或无法区分的玩耍不能确认打架。
跌倒：必须明确是真人，并看到从站立/行走到失衡、身体向地面倒下的时序变化；
已清楚看到真人失衡后倒地，即使随后双手撑地、起身或没有受伤，也可以确认跌倒，不需要额外证明伤情或跌倒原因。
单帧躺地、原本躺着、坐下、弯腰、蹲下或机器人/设备姿态不能确认跌倒。
observations 按时间逐项写出主体位置和具体可见动作，至少两项才能确认，不能只写“异常”“姿态可疑”。
assessment 必须忠实概括 observations：subject 为 human/non_human/uncertain，event 为 fight/fall/none/uncertain；
action 说明谁对谁做了什么，或谁如何失衡倒下，附可见时间变化；没有异常动作则填空字符串。
evidence 为支持动作变化的 observations 下标（从0开始），至少两项，且必须确实支持 action，不能引用正常交谈来支持打架。
evidence 引用的是最终输出的 observations 列表，不是输入图片编号或视频秒数；只有两条观察时完整引用必须写 [0,1]。
normalExcluded 仅在可见证据排除了正常动作解释时为 true；不能因为“无法证明正常”就设为 true。
输出前检查 reason、observations、normalExplanation、limitations 与 assessment 是否一致。
报告写“未见攻击/跌倒”“仅正常互动”“不能判断”时，不得输出 confirmed 或在 assessment 中改写成异常。
confirmed 仅用于报告明确支持对应异常、真人主体、至少两项时序证据且已排除正常解释的情况，自报高置信度不能替代证据。
清楚显示正常活动、明确排除本次假设时用 rejected，kind 为 none；看不清、缺动作过程或报告矛盾时用 uncertain。
不能将“没有看见异常”一律当作明确排除；不能把“无法排除异常”当作确认异常。
三种判定都必须提供中文分析报告。报告精简，观察2至3项，每项一句话，其余说明各一句话。"""

VERDICT_FORMAT = (
    '只返回 JSON：{"decision":"confirmed|rejected|uncertain","kind":"fight|fall|none",'
    '"confidence":0.0,"reason":"依据可见动作的判定摘要",'
    '"report":{"observations":["+时间：主体位置、具体动作及变化"],'
    '"normalExplanation":"是否符合正常活动，及排除或无法排除的具体依据",'
    '"limitations":"影响判断的遮挡、采样等限制，无则空字符串",'
    '"assessment":{"subject":"human|non_human|uncertain","event":"fight|fall|none|uncertain",'
    '"action":"具体异常动作及时间变化，没有则空字符串","evidence":[0,1],"normalExcluded":false}}}。'
    '枚举值只选一个；evidence 无有效异常证据时为 []，布尔值使用 JSON true/false。'
)


def parse_verdict(text, expected_kind, confidence_threshold=0.7):
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("复核结果必须是 JSON 对象")
    decision, kind, confidence = value.get("decision"), value.get("kind"), value.get("confidence")
    if decision not in ("confirmed", "rejected", "uncertain") or kind not in ("fight", "fall", "none"):
        raise ValueError("复核结果的判定或事件类型无效")
    if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("复核置信度无效")
    reason = value.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("复核结果缺少可见证据说明")
    if decision == "confirmed" and (kind != expected_kind or confidence < confidence_threshold):
        decision = "uncertain"
    if decision == "rejected" and kind != "none":
        raise ValueError("排除异常时 kind 应为 none")
    if decision == "rejected" and confidence < confidence_threshold:
        decision = "uncertain"
    report = value.get("report")
    if report is None:
        # Keep compatibility with older endpoints returning only an evidence reason.
        report = {"observations": [reason.strip()[:1000]], "normalExplanation": "", "limitations": ""}
    else:
        if not isinstance(report, dict):
            raise ValueError("分析报告必须是 JSON 对象")
        observations = report.get("observations")
        if not isinstance(observations, list) or not 1 <= len(observations) <= 8 or any(
                not isinstance(item, str) or not item.strip() for item in observations):
            raise ValueError("分析报告缺少有效的时序观察")
        for field in ("normalExplanation", "limitations"):
            if not isinstance(report.get(field, ""), str):
                raise ValueError("分析报告说明格式无效")
        report = {"observations": [item.strip()[:600] for item in observations],
                  "normalExplanation": report.get("normalExplanation", "").strip()[:1000],
                  "limitations": report.get("limitations", "").strip()[:1000]}
    assessment = value.get("report", {}).get("assessment") if isinstance(value.get("report"), dict) else None
    notes = []
    if isinstance(assessment, dict):
        assessment = dict(assessment)
        indexes = assessment.get("evidence")
        count = len(report["observations"])
        # A complete consecutive reference list can have an offset numbering origin.
        # shortcut: infer full-list references only, ambiguous partial references still fail validation.
        if (isinstance(indexes, list) and count >= 2 and len(indexes) == count
                and all(type(index) is int for index in indexes) and indexes[0] > 0
                and indexes == list(range(indexes[0], indexes[0] + count))):
            report["originalEvidence"] = indexes
            assessment["evidence"] = list(range(count))
            notes.append("模型完整引用了全部时序观察，但编号起点不为0；已按观察顺序统一编号，未增加视觉证据")
    issues = []
    if decision == "confirmed":
        if not isinstance(assessment, dict):
            issues.append("报告缺少具体异常动作与证据核对")
        else:
            if assessment.get("subject") != "human":
                issues.append("报告未明确异常主体为真人")
            if assessment.get("event") != expected_kind:
                issues.append("报告所述事件与异常结论不一致")
            action = assessment.get("action")
            if not isinstance(action, str) or not action.strip():
                issues.append("报告未说明具体异常动作")
            indexes = assessment.get("evidence")
            if (not isinstance(indexes, list) or len(indexes) < 2 or
                    any(type(index) is not int or not 0 <= index < len(report["observations"]) for index in indexes) or
                    indexes != sorted(set(indexes))):
                issues.append("报告缺少至少两项有效且按时序排列的动作证据")
            if assessment.get("normalExcluded") is not True or not report["normalExplanation"]:
                issues.append("报告尚未排除正常动作解释")
        if issues:
            decision = "uncertain"
            reason = "未确认异常：" + "；".join(issues) + "。模型原始说明：" + reason
    if isinstance(assessment, dict):
        report["assessment"] = {field: assessment.get(field) for field in
                                ("subject", "event", "action", "evidence", "normalExcluded")}
    if issues:
        report["validationIssues"] = issues
    if notes:
        report["validationNotes"] = notes
    # Derive the conclusion from the validated decision, never from a conflicting
    # model-written heading (e.g. low-confidence confirmation downgraded above).
    labels = {"confirmed": "打架" if expected_kind == "fight" else "跌倒",
              "rejected": "未打架" if expected_kind == "fight" else "未跌倒", "uncertain": "证据不足，无法确认"}
    report["conclusion"] = labels[decision]
    return {"decision": decision, "kind": kind, "confidence": confidence,
            "reason": reason.strip()[:1000], "report": report}


class ReviewFailure(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class VisionReviewer:
    def __init__(self, base_url="", model="", api_key="", timeout=45, confidence=0.7,
                 thinking=False, max_tokens=1200, thinking_tokens=512):
        self.base_url, self.model, self.api_key = base_url.rstrip("/"), model, api_key
        self.timeout, self.confidence = timeout, confidence
        self.thinking, self.max_tokens = thinking, max_tokens
        self.thinking_tokens = thinking_tokens
        if self.base_url:
            parsed = urlsplit(self.base_url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("VAD_VLM_BASE_URL 必须为无凭据的 HTTP(S) 接口地址")

    @property
    def configured(self):
        return bool(self.base_url and self.model)

    def review(self, kind, frames, evidence):
        if not self.configured:
            raise RuntimeError("大模型接口未配置")
        prompt = (
            "你是独立的视频异常复查员。下面是同一短视频可疑区域按时间排序的采样帧，保留周围上下文。"
            f"初筛提出的假设是 {kind}，你需独立审查，视频时长 {evidence['duration']} 秒。"
            f"可用触发前画面秒数为 {evidence.get('preTriggerSeconds', '未知')}，"
            f"触发后为 {evidence.get('postTriggerSeconds', '未知')}；若缺少靠近前的动作过程，应在判断限制中说明。"
            "两人靠近只是提交复核的触发条件，不是攻击证据。\n" + VERDICT_RULES + "\n" + VERDICT_FORMAT
        )
        content = []
        for frame in frames:
            content.extend([{"type": "text", "text": f"视频时间 +{frame['offset']:.3f}s"},
                            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + frame["jpeg"]}}])
        content.append({"type": "text", "text": prompt})
        if evidence.get("delegation"):
            content.append({"type": "text", "text": "JoyAI 的观察与待解决问题（仅供参考，请独立审查画面）：" +
                            str(evidence["delegation"])[:500]})
        body = {"model": self.model, "temperature": 0, "max_tokens": self.max_tokens, "stream": False,
                "response_format": {"type": "json_object"},
                "metadata": {"event_kind": kind},
                "messages": [{"role": "user", "content": content}]}
        if self.thinking:
            body["chat_template_kwargs"] = {"enable_thinking": True}
            body["thinking_token_budget"] = self.thinking_tokens
        else:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        request = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError("大模型响应过大")
            data = json.loads(raw)
            message = data["choices"][0]["message"]["content"]
            if not isinstance(message, str):
                raise ValueError("大模型响应缺少文本结果")
            if self.thinking and "</think>" in message:
                message = message.split("</think>", 1)[1].strip()
            return parse_verdict(message, kind, self.confidence)
        except urllib.error.HTTPError as exc:
            if exc.code in (502, 503, 504):
                raise RuntimeError(f"大模型接口返回 HTTP {exc.code}：推理上游不可用或超时，请检查模型服务和资源占用") from None
            raise RuntimeError(f"大模型接口返回 HTTP {exc.code}") from None
        except (OSError, urllib.error.URLError) as exc:
            cause = exc.reason if isinstance(exc, urllib.error.URLError) else exc
            if isinstance(cause, TimeoutError):
                raise ReviewFailure("REVIEW_TIMEOUT", f"大模型请求超时（{self.timeout:g} 秒），本次未确认异常；请检查推理耗时和服务负载") from None
            if isinstance(cause, ConnectionRefusedError) or getattr(cause, "errno", None) == errno.ECONNREFUSED:
                raise RuntimeError("大模型服务拒绝连接：服务未启动或端口未监听，请检查模型启动日志及内存/显存占用") from None
            raise RuntimeError("大模型连接失败，请检查接口地址、网络和模型服务状态") from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise ReviewFailure("REVIEW_INVALID_RESPONSE", "大模型返回格式无效，未确认异常") from None
