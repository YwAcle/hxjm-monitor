"""Pure local helpers. All business tools are discovered via CapabilityBridge."""
from datetime import datetime
import re

from PIL import Image
from pydantic import BaseModel, Field
from ai_infra.vision import decode_base64_image, image_to_data_url
from .base import ToolSpec
from .registry import ToolRegistry
from .time_parser import parse_time


class TimeParseArgs(BaseModel):
    text: str = Field(min_length=1, description="用户实际提供的时间表达，如明天下午3点、最近三天、两小时后；不要为没有时间要求的任务编造时间。")
    reference_time: datetime | None = Field(default=None, description="解析相对时间的基准，ISO 8601 格式，建议带时区偏移。仅在用户指定基准时填写；省略时使用当前时间。")
    timezone: str | None = Field(default=None, description="解析使用的 IANA 时区，如 Asia/Shanghai；省略时使用服务配置时区。")


class SuperResolutionArgs(BaseModel):
    # 图片由执行器从当前请求注入，模型无需生成庞大的 Base64 字符串。
    image_base64: str = Field(default="", description="由服务端从当前上传图片注入的 Data URL，模型应省略此参数；不要生成、复制或猜测 Base64。无图片时工具返回缺少图片状态。")
    prompt: str = Field(default="请将图片超分2倍", min_length=1, description="用户的图片放大要求，支持2倍或4倍，未指定时默认2倍；输出长边受4096像素限制。当前为插值放大，不支持生成新内容或恢复真实丢失细节。")


def super_resolve(prompt: str, image_base64: str | None = None) -> dict:
    """处理超分查询"""

    if not image_base64:
        return {
            "type": "super_resolution",
            "navigate_to": "super_resolution",
            "text": "请上传需要超分的图片。",
            "data": {"status": "missing_image", "description": "未提供输入图片"},
        }

    image = decode_base64_image(image_base64)
    if image is None:
        return {
            "type": "super_resolution",
            "navigate_to": "super_resolution",
            "text": "图片解码失败，请重新上传。",
            "data": {"status": "invalid_image", "description": "无法读取输入图片"},
        }

    # Pillow 的 bicubic 插值不依赖额外模型，适合在线请求中的低延迟放大。
    scale_match = re.search(r"(?:放大|超分|upscale)?\s*([24])\s*[xX倍]", prompt)
    scale = int(scale_match.group(1)) if scale_match else 2
    original_width, original_height = image.size
    max_side = 4096
    scale = min(scale, max_side / max(original_width, original_height))
    scale = max(1.0, scale)
    output_size = (
        max(1, round(original_width * scale)),
        max(1, round(original_height * scale)),
    )
    result_image = image.resize(output_size, resample=Image.Resampling.BICUBIC)
    result_data_url = image_to_data_url(
        result_image,
        max_side=max_side,
        jpeg_quality=92,
    )

    return {
        "type": "super_resolution",
        "navigate_to": "super_resolution",
        "text": f"图片超分完成：{output_size[0]}×{output_size[1]}。",
        "data": {
            "status": "success",
            "description": "图片已完成快速超分",
            "image_base64": result_data_url,
            "original_size": [original_width, original_height],
            "result_size": list(output_size),
            "scale": scale,
        }
    }


def build_default_registry(*, timezone="Asia/Shanghai"):
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "parse_time", "解析自然语言时间，返回带时区的时间范围；不查询业务数据、不执行预约。",
        TimeParseArgs, lambda a: parse_time(a.text, reference_time=a.reference_time,
                                           timezone=a.timezone or timezone).to_dict()))
    registry.register(ToolSpec(
        "super_resolve_image", "按明确要求用插值将上传图片放大2或4倍，最长边4096；不恢复真实细节。图片由服务器注入。",
        SuperResolutionArgs, lambda a: super_resolve(a.prompt, a.image_base64),
        context_inputs={"image_base64": "image_base64"}))
    return registry
