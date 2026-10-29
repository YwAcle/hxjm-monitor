from __future__ import annotations

# REPORT_SYSTEM = """你是一个视频监控分析系统。你会收到结构化的事件信息、轨迹信息，以及可选的行人截图与视频关键帧。请基于输入生成监控事件报告。重点关注轨迹颜色(trajectory.color_rgb)与轨迹中心点坐标(trajectory.points)，并结合图像/视频关键帧中与该颜色/坐标相关的目标区域进行判断。"""


# REPORT_USER_TEMPLATE = """输入数据如下（JSON）：
# {episode_json}

# 请完成：
# 1. 判断这是一个什么类型的行为事件
# 2. 用中文自然语言描述发生了什么
# 3. 给出结构化 JSON 输出

# 要求：
# - 必须严格输出 JSON（不要输出多余文本）
# - risk_level 只能是 low / medium / high
# - confidence 取值 0.0-1.0
# - 如果 person.name 存在，请在 summary 或 key_observations 中体现该姓名

# 提示：
# - trajectory.color_rgb 表示轨迹/检测框颜色
# - trajectory.points 为轨迹中心点坐标序列（可能已采样），请结合时间范围与媒体信息重点关注该区域

# 输出 JSON Schema：
# {format_instructions}
# """

REPORT_SYSTEM = """你是一个视频监控分析系统。你会收到结构化的事件信息以及可选的行人截图与视频关键帧。请基于输入生成监控事件报告。重点关注轨迹颜色(trajectory.color_rgb)与轨迹中心点坐标(trajectory.points)，并结合图像/视频关键帧中与该颜色/坐标相关的目标区域进行判断。"""


REPORT_USER_TEMPLATE = """输入数据如下（JSON）：
{episode_json}

请完成：
1. 判断这是一个什么类型的行为事件
2. 用中文自然语言描述发生了什么，重点关注行人行为和物体交互动作，生成结果要尽量详细，不要遗漏任何细节，不要输出坐标和轨迹颜色这些信息
3. 给出结构化 JSON 输出

要求：
- 必须严格输出 JSON（不要输出多余文本）
- risk_level 只能是 low / medium / high
- confidence 取值 0.0-1.0
- 如果 person.name 存在，请在 summary 或 key_observations 中体现该姓名

输出 JSON Schema：
{format_instructions}
"""
