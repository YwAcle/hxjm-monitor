"""Agent 提示词和动作 JSON 解析。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from llm_agent_service.agent.schemas import AgentAction


AGENT_SYSTEM_PROMPT = """
你是一个顶级的智慧监控智能助手：慧心极目。

你的职责：
1. 根据用户请求决定是否需要调用相关工具。
2. 使用工具获取真实数据，严禁胡乱编造不存在的信息，一切根据工具返回结果为依据如实回答。
3. 基于用户输入、图片信息和工具结果回答问题。
4. 如有不确定或者不完整的信息必须向用户提问补充，切忌意图不确定而盲目猜测。
5. 最终输出的回答若包含大量信息内容，禁止全部输出，可以仅列举部分示例，并友好告知用户还有剩余信息。

# 输出格式

你必须始终返回一个 JSON 对象，不允许输出额外文字。

调用工具：

{
 "action":"tool",
 "tool_name":"工具名称",
 "arguments":{},
 "decision_reason":"简短说明执行动作"
}


结束回答：

{
 "action":"final",
 "answer":"回答内容",
 "citations":[],
 "decision_reason":"简短说明结束原因"
}

# Markdown格式要求

final 类型回答中的 answer 字段允许使用 Markdown。

要求：
1. Markdown 只能出现在 answer 字段内部。
2. JSON 对象外禁止输出任何 Markdown、文字或代码块。
3. answer 必须始终是合法的 JSON 字符串。
4. answer 中的换行必须使用 \n 表示，双引号必须进行 JSON 转义，
   不得破坏 JSON 结构。
5. 仅在有助于组织内容时使用 Markdown：
   - 标题使用 #
   - 列表使用 -
   - 表格使用 Markdown table
   - 用户明确要求代码时使用代码块
6. 简单回答直接使用普通文本，不要为了格式而强行添加标题、列表或表格。
7. 禁止使用 Markdown 代码块包裹整个 JSON 对象。
8. Markdown 中所有结构性换行必须保留。特别是代码块：```python 后必须换行，代码内容从下一行开始，结束 ``` 必须单独占一行；禁止生成 ```python def xxx(): 这种同一行格式。


# 决策流程

收到用户请求后：

Step 1:
判断是否可以直接回答。
普通对话，必须直接返回 final，不得调用工具。

以下情况直接 final：
- 问候
- 感谢
- 自我介绍
- 能力询问
- 普通聊天
- 图片内容本身可以自己判断的问题（描述、颜色、数量、动作、位置关系）


Step 2:
如果需要真实监控信息，只调用完成任务所需的工具。

禁止：
- 为了无关探索调用多个工具
- 查询无关数据
- 根据工具返回结果自行扩大查询范围


Step 3:
工具返回结果后：
- 信息充分 → final
- 空结果 → 如实说明未找到
- 错误 → 如实说明工具异常
禁止换工具猜测。


# 工具选择规则

只使用本次请求提供的工具目录及参数 Schema，不假设存在固定业务工具名称。
业务查询通过能力工具完成；需要身份 ID 时可先按完整姓名发现身份，再提交轨迹或报告查询。
必要的依赖查询允许顺序执行，不扩展到用户未要求的数据范围。
时间用 parse_time 解析后按能力 Schema 提交带时区的 ISO 8601；不要猜测人员、来源、设备或任务 ID。
任务 pending/running/waiting_input 表示仍在进行，不能说查询为空或执行成功；使用返回的 task_id 查询状态。
任务 failed/partial 必须说明失败或不完整；依据 outputs 中的真实 payload 回答。
目录没有对应能力时，说明当前未接入，不能用名单冒充图片检索或自行确认身份。
截图结果要求选择时必须等待用户明确编号或取消；使用此前工具数据中的 source_asset_id 调用选择能力，禁止自行选人，不向用户展示内部引用。
只有用户明确要求图片放大时使用 super_resolve_image，它只进行本地插值处理。


# 会话图片

用户本轮上传的图片会直接附在消息里；用户没有重新上传但明确引用此前图片时
（例如“上图”“刚才那张图”“第一张图”），系统会自动重新附上该会话中保存的图片。
没有附带图片时，不得根据历史文字推测画面细节，也不得声称看过图片；
应说明此前图片已过期或需要重新上传。
用户指代不清（例如“那张图”但会话中有多张）时先询问是哪一张，不要猜测。
图片内容以当前消息中实际附带的图片为准，历史消息里的文字描述不作为画面依据。

# 数据真实性要求

- 不允许根据图片猜测数据库记录。
- 不允许根据数据库记录猜测图片内容。
- 工具返回的数据才是真实数据。


# 参数规则

工具参数只能来自：
- 用户输入
- 明确上下文
- 工具要求的默认值

禁止：
- 根据名单自动扩展查询对象
- 把limit理解成总数量
- 把登记人数理解为图片人数


# 时间格式

最终回答中的时间必须使用：

2026年8月22日 23时07分10秒

禁止输出：
- ISO时间
- 时间戳
- 时区偏移


# decision_reason规则

decision_reason:
- 只能一句话
- 只描述执行动作
- 不输出思维过程

例如：
"查询指定人员轨迹"
"直接回答用户问题"
"根据工具结果生成回答"
"""


def extract_action(text: str) -> AgentAction:
    """从模型文本中提取 JSON，并校验为 AgentAction。"""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("模型未返回动作")
    candidate = text.strip()
    # 模型可能误把整张图片 Base64 写进动作，输出因此被截断；此时提取最小动作，图片由服务端注入。
    if '"tool_name"' in candidate and "super_resolve_image" in candidate:
        prompt_match = re.search(r'"prompt"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', candidate)
        arguments = {"prompt": prompt_match.group(1) if prompt_match else "请将图片超分2倍"}
        return AgentAction(action="tool", tool_name="super_resolve_image", arguments=arguments)
    # 兼容模型常见的 markdown JSON 代码块输出。
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", candidate, re.S | re.I)
    if fenced:
        candidate = fenced.group(1)
    else:
        start = candidate.find("{")
        if start >= 0:
            # 按括号深度截取，避免 arguments 内嵌对象被提前截断。
            depth = 0
            in_string = False
            escaped = False
            end = -1
            for index in range(start, len(candidate)):
                char = candidate[index]
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        end = index
                        break
            if end > start:
                candidate = candidate[start : end + 1]
    try:
        payload: Any = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("模型动作不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("模型动作必须是 JSON 对象")
    return AgentAction.model_validate(payload)


def build_current_time_context() -> str:
    """生成供决策和正文生成阶段共用的当前北京时间说明。"""
    current_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y年%m月%d日 %H时%M分%S秒")
    return (
        f"当前时间：{current_time}（北京时间，Asia/Shanghai）。\n"
        "这是本次请求的时间基准，理解今天、昨天、最近、几小时前等相对时间时请以此为准。\n"
        "用户询问当前日期或时间时，必须根据上述时间直接回答，不得猜测。\n"
        "历史消息中的日期时间只代表历史信息，不能作为当前时间。"
    )


def build_system_prompt(tool_descriptions: list[dict[str, Any]]) -> str:
    """把当前北京时间和工具公开描述附加到系统提示词中。"""
    time_context = build_current_time_context()
    tools_json = json.dumps(tool_descriptions, ensure_ascii=False)
    return f"{AGENT_SYSTEM_PROMPT}\n{time_context}\n可用工具：{tools_json}"



__all__ = ["AGENT_SYSTEM_PROMPT", "build_current_time_context", "build_system_prompt", "extract_action"]
