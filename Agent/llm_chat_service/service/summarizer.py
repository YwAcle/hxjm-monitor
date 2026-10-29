from __future__ import annotations

from langchain_core.prompts import PromptTemplate

from llm_chat_service.llm.json_utils import extract_json
from langchain_core.messages import HumanMessage

from llm_chat_service.llm.model import ChatSGLang
from llm_chat_service.llm.prompts import CHAT_SUMMARY_SYSTEM, CHAT_SUMMARY_USER_TEMPLATE


def summarize(
    llm: ChatSGLang,
    query: str,
    time_range_json: str,
    person_json: str,
    frequency_json: str,
    tracklet_brief_json: str,
    report_brief_json: str,
    tracklet_limit: int,
    report_limit: int,
    max_new_tokens: int = 256,
) -> tuple[str, dict]:
    tmpl = PromptTemplate.from_template("""{system}\n\n{user}""")
    user = CHAT_SUMMARY_USER_TEMPLATE.format(
        query=query,
        time_range_json=time_range_json,
        person_json=person_json,
        frequency_json=frequency_json,
        tracklet_brief_json=tracklet_brief_json,
        report_brief_json=report_brief_json,
        tracklet_limit=int(tracklet_limit),
        report_limit=int(report_limit),
    )
    prompt = tmpl.format(system=CHAT_SUMMARY_SYSTEM, user=user)

    response = llm.invoke(
        [HumanMessage(content=prompt)],
        max_new_tokens=int(max_new_tokens),
    )
    raw = response.content if isinstance(response.content, str) else str(response.content)
    try:
        parsed = extract_json(raw)
    except Exception:
        parsed = {
            "answer_text": raw.strip(),
            "anomalies": [],
            "timeline": [],
        }

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = raw[:start].strip()
    else:
        text = raw.strip()

    if not isinstance(parsed, dict):
        parsed = {
            "answer_text": text,
            "anomalies": [],
            "timeline": [],
        }
    if "answer_text" not in parsed or not isinstance(parsed.get("answer_text"), str):
        parsed["answer_text"] = text
    if "anomalies" not in parsed or not isinstance(parsed.get("anomalies"), list):
        parsed["anomalies"] = []
    if "timeline" not in parsed or not isinstance(parsed.get("timeline"), list):
        parsed["timeline"] = []

    return text, parsed
