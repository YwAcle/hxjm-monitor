"""将现有 ReidService 能力包装为只读 Agent 工具。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from llm_agent_service.service.reid_service import ReidService
from llm_agent_service.service.gallery_search import GallerySearchService
from llm_agent_service.tools.base import ToolSpec
from llm_agent_service.tools.registry import ToolRegistry
from llm_agent_service.tools.time_parser import parse_time


class TimeParseArgs(BaseModel):
    text: str = Field(min_length=1, description="用户实际提供的时间表达，如明天下午3点、最近三天、两小时后；不要为没有时间要求的任务编造时间。")
    reference_time: datetime | None = Field(default=None, description="解析相对时间的基准，ISO 8601 格式，建议带时区偏移。仅在用户指定基准时填写；省略时使用当前时间。")
    timezone: str | None = Field(default=None, description="解析使用的 IANA 时区，如 Asia/Shanghai；省略时使用服务配置时区。")


class PersonArgs(BaseModel):
    query: str = Field(min_length=1, description="包含已登记完整姓名的文本，可含多个姓名；姓名应来自用户请求或与当前任务相关的明确上下文。按姓名字符串匹配，不支持人脸、衣着、外貌、人员 ID 或模糊身份检索；不要从名单中随意挑选姓名。")


class PersonQueryArgs(PersonArgs):
    time_prompt: str = Field(default="今天", min_length=1, description="用户指定的查询时间范围，如昨天、最近三天；可沿用当前任务明确的时间条件。省略时按今天查询，这是系统默认值，不代表用户明确指定了今天；不要自行改写用户的时间范围。")
    limit: int = Field(default=20, ge=1, le=100, description="最多返回的记录条数，1～100，默认20；这不是全量统计。用户只问最近一次时设为1；不要把返回条数当作人数或数据库总数。")


class ReportQueryArgs(BaseModel):
    time_prompt: str = Field(default="今天", min_length=1, description="用户指定的报告查询时间范围，如昨天或最近三天；省略时按今天查询，这是系统默认值。只用于筛选已有报告，不用于安排未来任务。")
    limit: int = Field(default=20, ge=1, le=100, description="最多返回的记录条数，1～100，默认20；这不是全量统计。用户只问最近一次时设为1；不要把返回条数当作人数或数据库总数。")


class VadArgs(BaseModel):
    time_prompt: str = Field(default="今天", min_length=1, description="用户指定的查询时间范围，如昨天、最近三天；可沿用当前任务明确的时间条件。省略时按今天查询，这是系统默认值，不代表用户明确指定了今天；不要自行改写用户的时间范围。")
    limit: int = Field(default=20, ge=1, le=100, description="最多返回的记录条数，1～100，默认20；这不是全量统计。用户只问最近一次时设为1；不要把返回条数当作人数或数据库总数。")
    mode: Literal["range", "latest"] = Field(default="range", description="range：按 time_prompt 查询；latest：查询数据库最新记录，不受 time_prompt 时间范围限制。最近一次/最新用 latest，最近三天等时长范围用 range；默认 range。")


class SuperResolutionArgs(BaseModel):
    # 图片由执行器从当前请求注入，模型无需生成庞大的 Base64 字符串。
    image_base64: str = Field(default="", description="由服务端从当前上传图片注入的 Data URL，模型应省略此参数；不要生成、复制或猜测 Base64。无图片时工具返回缺少图片状态。")
    prompt: str = Field(default="请将图片超分2倍", min_length=1, description="用户的图片放大要求，支持2倍或4倍，未指定时默认2倍；输出长边受4096像素限制。当前为插值放大，不支持生成新内容或恢复真实丢失细节。")


class EmptyArgs(BaseModel):
    """无参数工具使用独立模型，避免直接使用 Pydantic BaseModel。"""

    pass


class ImageSearchArgs(BaseModel):
    image_base64: str = Field(default="", description="服务器从本次上传图片注入，模型必须省略，不得生成或复制 Base64。第一版要求单人裁剪图。")
    top_k: int = Field(default=5, ge=1, le=10, description="最多返回的相似登记照片数；相似度不是身份正确率。")


class DescriptionSearchArgs(BaseModel):
    description: str = Field(min_length=1, max_length=200,
                             description="用户明确提供的衣着、颜色、携带物品等外观条件，压缩为简短短语，不翻译、不扩写、不补姓名/时间/地点；不得编造。")
    top_k: int = Field(default=5, ge=1, le=10, description="最多返回的相似登记照片数，不是全库统计。")


def _display_time(service: ReidService, value: datetime | None) -> str | None:
    """将数据库时间转成面向中文用户展示的北京时间，保留秒级精度。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = service.timezone.localize(value)
    else:
        value = value.astimezone(service.timezone)
    return value.strftime("%Y年%m月%d日 %H时%M分%S秒")


def _parse_time(service: ReidService, args: TimeParseArgs) -> dict[str, Any]:
    """向 Agent 返回独立于数据库查询的统一时间解析结构。"""
    timezone = args.timezone or service.timezone.zone
    return parse_time(
        args.text,
        reference_time=args.reference_time,
        timezone=timezone,
    ).to_dict()


def _find_person(service: ReidService, query: str) -> dict[str, Any]:
    names = service._detect_person_names(query)
    return {"names": names, "person_ids": service._get_person_ids(names)}


def _tracklets(service: ReidService, args: PersonQueryArgs) -> dict[str, Any]:
    from llm_chat_service.db.tracklet_repo import list_tracklets_for_persons
    names = service._detect_person_names(args.query)
    person_ids = service._get_person_ids(names)
    time_range = service._parse_time_range(args.time_prompt)
    rows = list_tracklets_for_persons(service.engine, service.schema, person_ids, time_range.start_ts, time_range.end_ts, limit=args.limit)
    return {"person_names": names, "person_ids": person_ids, "count": len(rows), "items": [
        {"start_ts": _display_time(service, row.start_ts), "camera": service._get_camera_from_stream_id(row.stream_id)} for row in rows
    ]}


def _reports(service: ReidService, args: PersonQueryArgs) -> dict[str, Any]:
    from llm_chat_service.db.report_repo import list_reports_for_persons
    names = service._detect_person_names(args.query)
    person_ids = service._get_person_ids(names)
    time_range = service._parse_time_range(args.time_prompt)
    rows = list_reports_for_persons(service.engine, service.schema, person_ids, time_range.start_ts, time_range.end_ts, limit=args.limit)
    return {"person_names": names, "count": len(rows), "items": [
        {"report": item.get("report").report_text if item.get("report") else ""} for item in rows
    ]}


def _reports_by_time(service: ReidService, args: ReportQueryArgs) -> dict[str, Any]:
    """查询指定时间内的全部报告，不要求先指定人员。"""
    from llm_chat_service.db.report_repo import list_reports_global

    time_range = service._parse_time_range(args.time_prompt)
    rows = list_reports_global(
        service.engine,
        service.schema,
        time_range.start_ts,
        time_range.end_ts,
        limit=args.limit,
    )
    return {
        "time_range": {
            "start_ts": time_range.start_ts.isoformat(),
            "end_ts": time_range.end_ts.isoformat(),
        },
        "count": len(rows),
        "items": [
            {
                "id": row.id,
                "episode_id": row.episode_id,
                "prompt_type": row.prompt_type,
                "report_text": row.report_text or "",
                "report_json": row.report_json,
                "created_at": _display_time(service, row.created_at),
                "event_start_ts": _display_time(service, row.episode_start_ts),
                "event_end_ts": _display_time(service, row.episode_end_ts),
            }
            for row in rows
        ],
    }


def _vad(service: ReidService, args: VadArgs) -> dict[str, Any]:
    from llm_api_service.db.vad_repo import list_recent_vad_anomalies, list_vad_anomalies
    latest_words = ("最近一次", "最新", "离现在最近", "last", "latest", "most recent")
    is_latest = args.mode == "latest" or any(word in args.time_prompt.lower() for word in latest_words)
    if is_latest:
        rows = list_recent_vad_anomalies(service.engine, service.schema, limit=args.limit)
    else:
        time_range = service._parse_time_range(args.time_prompt)
        rows = list_vad_anomalies(service.engine, service.schema, time_range.start_ts, time_range.end_ts, limit=args.limit)
    return {"count": len(rows), "items": [
        {
            "id": row.id,
            "created_at": _display_time(service, row.created_at),
            "anomaly_name": row.anomaly_name,
            "camera": service._get_camera_from_stream_id(row.stream_id),
        }
        for row in rows
    ]}


def _list_known_persons(service: ReidService) -> dict[str, Any]:
    """读取熟人缓存，避免为展示列表重复查询数据库。"""
    with service._known_persons_lock:
        persons = [
            {"name": name, "person_ids": list(person_ids)}
            for name, person_ids in service.known_persons.items()
        ]
    return {"count": len(persons), "persons": persons}


def _super_resolve(service: ReidService, args: SuperResolutionArgs) -> dict[str, Any]:
    """复用现有快速超分实现，保持前端已有返回结构。"""
    result = service._process_super_resolution_query(args.prompt, args.image_base64)
    return {"type": result.get("type"), "text": result.get("text"), "data": result.get("data")}


def build_default_registry(service: ReidService, gallery_search: GallerySearchService | None = None) -> ToolRegistry:
    """创建本服务默认的最小只读工具集合。"""
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "parse_time",
        "解析用户输入中的自然语言时间表达，返回 datetime、range 或 duration 类型的结构化时间；"
        "适用于今天、明天、后天、下周、下个月、几小时后、几天后、上午/下午/晚上和具体日期时间。"
        "仅在用户需要解释时间含义或任务确实需要独立时间解析时使用；轨迹、报告和异常查询已有时间参数，无需例行先调用本工具。返回解析结果，不执行数据库查询、提醒或预约。",
        TimeParseArgs,
        lambda a: _parse_time(service, a),
    ))
    registry.register(ToolSpec("find_person", "按输入中包含的完整姓名匹配已登记人员，适用于用户询问某人是否登记或需要解析已知姓名。返回匹配姓名和关联人员ID；空结果仅表示没有匹配到姓名。不能识别上传图片中的身份，不支持按外貌找人，也不能判断人员是否在场。", PersonArgs, lambda a: _find_person(service, a.query)))
    registry.register(ToolSpec("query_person_tracklets", "查询明确指定人员在时间范围内的已有监控轨迹，适用于询问某人何时出现、去过哪些摄像头位置。必须有来自当前任务的姓名；工具内部完成姓名和时间解析，无需例行先列人员或解析时间。返回本次记录数及出现时间、摄像头；空结果表示本次查询没有轨迹。不能据此识别上传图片中的人、统计图片人数或证明某人在图片里。", PersonQueryArgs, lambda a: _tracklets(service, a)))
    registry.register(ToolSpec("query_person_reports", "查询明确指定人员在时间范围内关联的已有大模型监控报告，适用于询问该人员的历史事件描述。必须有当前任务相关的姓名；返回匹配姓名、记录数和报告文本。无指定人员的时间范围报告查询使用 query_reports_by_time。不会分析当前上传图片或生成新的监控报告；空结果不证明该人员没有活动。", PersonQueryArgs, lambda a: _reports(service, a)))
    registry.register(ToolSpec("query_reports_by_time", "按时间范围查询已有大模型监控事件报告，适用于未指定人员的历史报告查询。无需先查人员名单或编造姓名。返回查询时间范围、本次记录数及报告ID、事件时间、文本和结构化报告等；受limit限制，不代表全部记录总数。不会对上传图片生成报告；如需指定人员的报告，使用 query_person_reports。", ReportQueryArgs, lambda a: _reports_by_time(service, a)))
    registry.register(ToolSpec("query_vad_events", "查询数据库中已经记录的异常事件，返回本次记录数、事件ID、记录时间、异常名称和摄像头。询问最近一次/最新异常时使用mode=latest，通常limit=1；最近三天等范围使用mode=range。实现也会将time_prompt包含最近一次、最新等表达视为最新查询。不能检测当前上传图片是否异常；空结果仅说明本次查询没有记录。", VadArgs, lambda a: _vad(service, a)))
    registry.register(ToolSpec("list_known_persons", "列出服务当前缓存的已登记人员，适用于询问登记名单、登记人数，或任务明确需要该名单的情况。无参数，传空对象。返回姓名、关联人员ID和登记姓名数量；同一姓名可关联多个ID。登记名单不表示当前在场人员，不能用于图片计数或身份识别；不要仅因问题涉及人就调用，也不要将它作为所有人员查询的前置步骤。", EmptyArgs, lambda a: _list_known_persons(service)))
    registry.register(ToolSpec("super_resolve_image", "在用户明确要求放大、超分或增强上传图片时使用，返回处理状态及图片结果；支持2倍或4倍并受尺寸上限约束。图片由服务端注入，无图片时返回上传提示。不会识别人物身份、查询监控或恢复真实缺失细节；只需描述、计数、读图时直接依据图片回答，无需调用此工具。", SuperResolutionArgs, lambda a: _super_resolve(service, a)))
    if gallery_search is not None:
        registry.register(ToolSpec(
            "search_pedestrians_in_screenshot",
            "用户要求用监控截图、含多人或人数不明确的图片找登记行人时使用。单人自动提特征检索；多人返回候选框等待用户明确选择；无人时提示重传。不能自行挑最大框或最高分框。图片由服务器注入。",
            ImageSearchArgs, lambda a: gallery_search.search_screenshot(a.image_base64, a.top_k),
        ))
        registry.register(ToolSpec(
            "search_pedestrians_by_image",
            "用户明确要求用上传的单人图片查找相似登记行人时使用。只搜索 reid_target 有效登记库，"
            "通过 CLIP-ReID 服务对登记照片和查询图提取同一特征空间的特征，返回候选姓名、ID、照片和相似度。图片由服务器注入。"
            "模型或接口不可用时如实说明未执行匹配；不能用姓名名单替代。不是身份确认，不查实时摄像头、历史轨迹或出现时间。",
            ImageSearchArgs, lambda a: gallery_search.search_image(a.image_base64, a.top_k),
        ))
        registry.register(ToolSpec(
            "search_pedestrians_by_description",
            "用户主动按衣着、颜色、背包等外观描述找登记行人时使用。调用远端 Chinese-CLIP 文本特征接口，"
            "把描述编码为与登记照片同一特征空间的向量，在最多2000条有效登记记录中按余弦相似度返回候选姓名、ID、照片和相似度。"
            "结果是相似度排序，不是身份确认；没有校准阈值，不能把首位当作命中。gallery_truncated=true表示只搜索了部分登记记录。"
            "不支持按时间、摄像头筛选，不查历史出现记录；登记照片外观可能不同于当前外观。"
            "文本服务不可用时说明未完成检索，不得说没有匹配。普通图片描述、读图或数人无需调用。",
            DescriptionSearchArgs, lambda a: gallery_search.search_description(a.description, a.top_k),
        ))
    return registry


__all__ = ["build_default_registry"]
