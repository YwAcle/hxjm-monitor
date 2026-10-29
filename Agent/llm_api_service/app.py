"""
Flask 应用入口
"""
from __future__ import annotations

import json

from flask import Flask, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix

from llm_api_service.config import DbConfig, OpenRouterConfig, PlaybackConfig, ServiceConfig
from llm_api_service.agent.monitor_agent import StructuredMonitorAgent


def create_app(
    *,
    engine,
    db_cfg: DbConfig,
    openrouter_cfg: OpenRouterConfig,
    playback_cfg: PlaybackConfig,
    svc_cfg: ServiceConfig,
) -> Flask:
    """
    创建 Flask 应用
    
    Args:
        engine: 数据库引擎
        db_cfg: 数据库配置
        openrouter_cfg: OpenRouter 配置
        playback_cfg: 回放服务配置
        svc_cfg: 服务配置
        
    Returns:
        Flask 应用实例
    """
    app = Flask(__name__)
    
    # 配置代理支持
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
        x_port=1,
        x_prefix=1,
    )
    
    # 初始化 Agent
    agent = StructuredMonitorAgent(
        openrouter_config=openrouter_cfg,
        playback_config=playback_cfg,
        service_config=svc_cfg,
        engine=engine,
        schema=db_cfg.schema,
        verbose=True,
    )
    
    @app.post("/chat")
    def chat():
        """
        文本问答接口
        
        请求体:
        {
            "prompt": "今天张嘉豪干了什么"
        }
        
        响应:
        {
            "type": "reid_result",
            "title": "REID行人结果如下",
            "summary": "...",
            ...
        }
        """
        payload = request.get_json(silent=True) or {}
        prompt = payload.get("prompt")
        
        if prompt is None or str(prompt).strip() == "":
            return jsonify({"error": "missing prompt"}), 400
        
        try:
            # 运行 Agent
            result = agent.run(query=str(prompt), image_bytes=None)
            
            if result.get("type") == "error":
                return jsonify({
                    "error": result.get("error", "未知错误"),
                    "query": prompt,
                }), 500
            
            return jsonify(result)
            
        except Exception as e:
            return jsonify({
                "error": str(e),
                "query": prompt,
            }), 500
    
    @app.post("/chat_with_image")
    def chat_with_image():
        """
        带图片的问答接口
        
        请求: multipart/form-data
        - prompt: 文本问题
        - file: 图片文件
        """
        prompt = request.form.get("prompt") or request.args.get("prompt")
        
        if prompt is None or str(prompt).strip() == "":
            return jsonify({"error": "missing prompt"}), 400
        
        file = request.files.get("file")
        if file is None:
            return jsonify({"error": "missing file"}), 400
        
        image_bytes = file.read()
        
        try:
            # 运行 Agent
            result = agent.run(query=str(prompt), image_bytes=image_bytes)
            
            if result.get("type") == "error":
                return jsonify({
                    "error": result.get("error", "未知错误"),
                    "query": prompt,
                }), 500
            
            return jsonify(result)
            
        except Exception as e:
            return jsonify({
                "error": str(e),
                "query": prompt,
            }), 500
    
    @app.get("/tools")
    def list_tools():
        """
        列出所有可用工具
        """
        tools = [
            {
                "name": "parse_time_range",
                "description": "解析时间范围，支持今天、昨天、本周、上周、最近N天等",
            },
            {
                "name": "get_person_by_name",
                "description": "根据姓名查找人员信息",
            },
            {
                "name": "list_tracklets_for_person",
                "description": "获取指定人员在时间范围内的轨迹记录",
            },
            {
                "name": "list_vad_anomalies",
                "description": "获取时间范围内的异常检测结果（跌倒、打架、烟雾等）",
            },
            {
                "name": "list_reports_by_time",
                "description": "获取时间范围内的详细事件报告",
            },
            {
                "name": "build_playback_url",
                "description": "构建视频回放URL",
            },
        ]
        return jsonify({"tools": tools})
    
    @app.get("/health")
    def health():
        """健康检查"""
        return jsonify({"status": "ok"})
    
    @app.get("/")
    def index():
        """首页"""
        return jsonify({
            "service": "LLM API Service",
            "version": "0.1.0",
            "description": "基于 LangChain + OpenRouter 的智能监控问答服务",
            "endpoints": {
                "/chat": "POST - 文本问答",
                "/chat_with_image": "POST - 带图片问答",
                "/tools": "GET - 列出可用工具",
                "/health": "GET - 健康检查",
            },
        })
    
    return app

