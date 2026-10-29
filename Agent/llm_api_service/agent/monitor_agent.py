"""
监控系统 Agent - 自定义 ReAct 实现
兼容 LangChain 1.x 新版本
"""
from __future__ import annotations

import json
import re
from typing import Optional, Any

from llm_api_service.config import OpenRouterConfig, PlaybackConfig, ServiceConfig
from llm_api_service.llm.openrouter import OpenRouterLLM
from llm_api_service.tools.time_parser import parse_time_range_func
from llm_api_service.tools.person_tools import (
    get_person_by_name_func,
    list_tracklets_for_person_func,
    set_db_context as set_person_db_context,
)
from llm_api_service.tools.anomaly_tools import (
    list_vad_anomalies_func,
    list_reports_by_time_func,
    set_db_context as set_anomaly_db_context,
)


# 工具定义
TOOLS = {
    "parse_time_range": {
        "func": parse_time_range_func,
        "description": "解析时间范围，将'今天'、'昨天'、'上周'等转换为具体时间。输入：包含时间信息的字符串。",
        "params": ["query"],
    },
    "get_person_by_name": {
        "func": get_person_by_name_func,
        "description": "根据姓名查找人员信息。输入：人员姓名。",
        "params": ["name"],
    },
    "list_tracklets_for_person": {
        "func": list_tracklets_for_person_func,
        "description": "获取指定人员在时间范围内的轨迹记录。输入：person_id, start_ts, end_ts。",
        "params": ["person_id", "start_ts", "end_ts"],
    },
    "list_vad_anomalies": {
        "func": list_vad_anomalies_func,
        "description": "获取时间范围内的异常检测结果（跌倒、打架、烟雾等）。输入：start_ts, end_ts。",
        "params": ["start_ts", "end_ts"],
    },
    "list_reports_by_time": {
        "func": list_reports_by_time_func,
        "description": "获取时间范围内的详细事件报告。输入：start_ts, end_ts。",
        "params": ["start_ts", "end_ts"],
    },
}


def get_tools_description() -> str:
    """生成工具描述文本"""
    lines = []
    for name, info in TOOLS.items():
        lines.append(f"- {name}: {info['description']}")
    return "\n".join(lines)


class StructuredMonitorAgent:
    """
    结构化监控 Agent - 自定义 ReAct 实现
    """
    
    def __init__(
        self,
        openrouter_config: OpenRouterConfig,
        playback_config: PlaybackConfig,
        service_config: ServiceConfig,
        engine,
        schema: str = "public",
        verbose: bool = True,
    ):
        self.openrouter_config = openrouter_config
        self.playback_config = playback_config
        self.service_config = service_config
        self.engine = engine
        self.schema = schema
        self.verbose = verbose
        self.max_iterations = service_config.max_iterations
        
        # 设置数据库上下文
        set_person_db_context(engine, schema, playback_config)
        set_anomaly_db_context(engine, schema, playback_config)
        
        # 创建 LLM
        self.llm = OpenRouterLLM(config=openrouter_config)
        
        # 存储工具调用结果
        self.tool_results = {}
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        tools_desc = get_tools_description()
        tool_names = ", ".join(TOOLS.keys())
        
        return f"""你是一个智能监控系统助手，能够回答关于人员活动和异常事件的问题。

你有以下工具可用：
{tools_desc}

使用策略：
- 如果用户询问某人的活动（如"张嘉豪今天干了什么"）：
  1. 先用 parse_time_range 解析时间
  2. 用 get_person_by_name 查找人员
  3. 用 list_tracklets_for_person 获取轨迹

- 如果用户询问异常事件（如"昨天有什么异常"）：
  1. 先用 parse_time_range 解析时间
  2. 用 list_vad_anomalies 获取异常检测结果
  3. 用 list_reports_by_time 获取详细报告

使用以下格式回答：

Thought: 你的思考
Action: 工具名称（必须是 [{tool_names}] 中的一个）
Action Input: 参数（JSON格式，如 {{"query": "今天"}} 或 {{"name": "张嘉豪"}}）

观察到工具返回结果后：
Observation: 工具返回的结果

继续思考直到有足够信息，然后输出：
Thought: 我现在知道最终答案了
Final Answer: 对原始问题的最终回答（用中文）

重要：
- 每次只调用一个工具
- Action Input 必须是有效的 JSON 格式
- 最终答案请用中文总结"""
    
    def _parse_action(self, text: str) -> tuple[Optional[str], Optional[dict]]:
        """解析 LLM 输出中的 Action 和 Action Input"""
        # 匹配 Action
        action_match = re.search(r"Action:\s*(\w+)", text)
        if not action_match:
            return None, None
        
        action = action_match.group(1).strip()
        
        # 匹配 Action Input (JSON 格式)
        input_match = re.search(r"Action Input:\s*(\{.*?\})", text, re.DOTALL)
        if input_match:
            try:
                action_input = json.loads(input_match.group(1))
                return action, action_input
            except json.JSONDecodeError:
                pass
        
        # 尝试匹配简单字符串输入
        input_match = re.search(r"Action Input:\s*[\"']?([^\"'\n]+)[\"']?", text)
        if input_match:
            # 获取工具的第一个参数名
            if action in TOOLS:
                param_name = TOOLS[action]["params"][0]
                return action, {param_name: input_match.group(1).strip()}
        
        return action, {}
    
    def _parse_final_answer(self, text: str) -> Optional[str]:
        """解析最终答案"""
        match = re.search(r"Final Answer:\s*(.*?)$", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
    
    def _call_tool(self, action: str, action_input: dict) -> str:
        """调用工具"""
        if action not in TOOLS:
            return json.dumps({"error": f"未知工具: {action}"}, ensure_ascii=False)
        
        tool = TOOLS[action]
        try:
            if self.verbose:
                print(f"[工具调用] {action}({action_input})")
            
            result = tool["func"](**action_input)
            
            # 存储结果
            self.tool_results[action] = result
            
            if self.verbose:
                result_str = json.dumps(result, ensure_ascii=False, indent=2)
                print(f"[工具结果] {result_str[:500]}...")
            
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            error_result = {"error": str(e)}
            if self.verbose:
                print(f"[工具错误] {e}")
            return json.dumps(error_result, ensure_ascii=False)
    
    def run(self, query: str, image_bytes: Optional[bytes] = None) -> dict:
        """
        运行 Agent 并返回结构化结果
        """
        self.tool_results = {}  # 重置工具结果
        
        try:
            system_prompt = self._build_system_prompt()
            
            # 构建对话
            conversation = f"{system_prompt}\n\n用户问题: {query}\n\n"
            
            if self.verbose:
                print("=" * 60)
                print(f"用户问题: {query}")
                print("=" * 60)
            
            for iteration in range(self.max_iterations):
                if self.verbose:
                    print(f"\n--- 迭代 {iteration + 1}/{self.max_iterations} ---")
                
                # 调用 LLM
                response = self.llm._call(conversation)
                
                if self.verbose:
                    print(f"[LLM 响应]\n{response[:500]}...")
                
                # 检查是否有最终答案
                final_answer = self._parse_final_answer(response)
                if final_answer:
                    if self.verbose:
                        print(f"\n[最终答案] {final_answer}")
                    
                    # 构建结构化响应
                    return self._build_structured_response(query, final_answer)
                
                # 解析 Action
                action, action_input = self._parse_action(response)
                
                if action and action_input is not None:
                    # 调用工具
                    observation = self._call_tool(action, action_input)
                    
                    # 更新对话
                    conversation += f"{response}\nObservation: {observation}\n\n"
                else:
                    # 没有有效的 Action，添加响应继续
                    conversation += f"{response}\n\n"
            
            # 达到最大迭代次数
            return {
                "type": "error",
                "error": f"达到最大迭代次数 ({self.max_iterations})",
                "query": query,
                "tool_results": self.tool_results,
            }
            
        except Exception as e:
            import traceback
            return {
                "type": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
                "query": query,
            }
    
    def _build_structured_response(self, query: str, summary: str) -> dict:
        """根据工具调用结果构建结构化响应"""
        
        # 判断查询类型
        if "list_tracklets_for_person" in self.tool_results or "get_person_by_name" in self.tool_results:
            return self._build_reid_response(query, summary)
        elif "list_vad_anomalies" in self.tool_results or "list_reports_by_time" in self.tool_results:
            return self._build_vad_response(query, summary)
        else:
            return self._build_general_response(query, summary)
    
    def _build_reid_response(self, query: str, summary: str) -> dict:
        """构建 ReID 响应"""
        response = {
            "type": "reid_result",
            "title": "REID行人结果如下",
            "summary": summary,
            "query": query,
        }
        
        # 提取时间范围
        if "parse_time_range" in self.tool_results:
            tr = self.tool_results["parse_time_range"]
            if isinstance(tr, dict):
                response["time_range"] = {
                    "start": tr.get("start_ts"),
                    "end": tr.get("end_ts"),
                    "label": tr.get("label"),
                }
        
        # 提取人员信息
        if "get_person_by_name" in self.tool_results:
            person = self.tool_results["get_person_by_name"]
            if isinstance(person, dict) and person.get("found"):
                response["person"] = {
                    "id": person.get("id"),
                    "name": person.get("name"),
                }
        
        # 提取轨迹信息
        if "list_tracklets_for_person" in self.tool_results:
            tracklets_data = self.tool_results["list_tracklets_for_person"]
            if isinstance(tracklets_data, dict):
                response["total_count"] = tracklets_data.get("total_count", 0)
                response["camera_stats"] = tracklets_data.get("camera_stats", [])
                response["tracklets"] = tracklets_data.get("tracklets", [])
        
        return response
    
    def _build_vad_response(self, query: str, summary: str) -> dict:
        """构建 VAD 响应"""
        response = {
            "type": "vad_result",
            "title": "VAD异常结果如下",
            "summary": summary,
            "query": query,
        }
        
        # 提取时间范围
        if "parse_time_range" in self.tool_results:
            tr = self.tool_results["parse_time_range"]
            if isinstance(tr, dict):
                response["time_range"] = {
                    "start": tr.get("start_ts"),
                    "end": tr.get("end_ts"),
                    "label": tr.get("label"),
                }
        
        # 提取 VAD 异常
        if "list_vad_anomalies" in self.tool_results:
            vad_data = self.tool_results["list_vad_anomalies"]
            if isinstance(vad_data, dict):
                response["total_count"] = vad_data.get("total_count", 0)
                response["level_stats"] = vad_data.get("level_stats", {})
                response["type_stats"] = vad_data.get("type_stats", {})
                response["anomalies"] = vad_data.get("anomalies", [])
        
        # 提取 LLM 报告
        if "list_reports_by_time" in self.tool_results:
            reports_data = self.tool_results["list_reports_by_time"]
            if isinstance(reports_data, dict):
                response["reports"] = reports_data.get("reports", [])
                response["risk_stats"] = reports_data.get("risk_stats", {})
        
        return response
    
    def _build_general_response(self, query: str, summary: str) -> dict:
        """构建通用响应"""
        return {
            "type": "general_result",
            "title": "查询结果",
            "summary": summary,
            "query": query,
            "tool_results": self.tool_results,
        }


# 保持向后兼容
def create_monitor_agent(
    openrouter_config: OpenRouterConfig,
    playback_config: PlaybackConfig,
    service_config: ServiceConfig,
    engine,
    schema: str = "public",
    verbose: bool = True,
):
    """创建监控 Agent（返回 StructuredMonitorAgent 实例）"""
    return StructuredMonitorAgent(
        openrouter_config=openrouter_config,
        playback_config=playback_config,
        service_config=service_config,
        engine=engine,
        schema=schema,
        verbose=verbose,
    )
