"""
LLM API Service 启动脚本
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 确保可以导入 llm_api_service
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_api_service.app import create_app
from llm_api_service.config import DbConfig, OpenRouterConfig, PlaybackConfig, ServiceConfig
from llm_api_service.db.session import create_pg_engine


def main():
    parser = argparse.ArgumentParser(
        description="LLM API Service - 基于 LangChain + OpenRouter 的智能监控问答服务"
    )
    
    # 服务配置
    parser.add_argument("--host", type=str, default="0.0.0.0", help="服务监听地址")
    parser.add_argument("--port", type=int, default=8003, help="服务端口")
    
    # OpenRouter 配置
    parser.add_argument(
        "--openrouter-api-key",
        type=str,
        default=os.getenv("OPENROUTER_API_KEY", ""),
        help="OpenRouter API Key",
    )
    parser.add_argument(
        "--openrouter-model",
        type=str,
        default=os.getenv("OPENROUTER_MODEL", "minimax/minimax-m2"),
        help="OpenRouter 模型名称",
    )
    parser.add_argument(
        "--openrouter-max-tokens",
        type=int,
        default=int(os.getenv("OPENROUTER_MAX_TOKENS", "2048")),
        help="最大生成 token 数",
    )
    parser.add_argument(
        "--openrouter-temperature",
        type=float,
        default=float(os.getenv("OPENROUTER_TEMPERATURE", "0.1")),
        help="温度参数",
    )
    
    # 数据库配置
    parser.add_argument("--db-host", type=str, default=os.getenv("DB_HOST", "192.168.108.238"))
    parser.add_argument("--db-port", type=int, default=int(os.getenv("DB_PORT", "5432")))
    parser.add_argument("--db-user", type=str, default=os.getenv("DB_USER", "root"))
    parser.add_argument("--db-password", type=str, default=os.getenv("DB_PASSWORD", "123456"))
    parser.add_argument("--db-name", type=str, default=os.getenv("DB_NAME", "postgres"))
    parser.add_argument("--db-schema", type=str, default=os.getenv("DB_SCHEMA", "public"))
    
    # 回放服务配置
    parser.add_argument(
        "--playback-host",
        type=str,
        default=os.getenv("PLAYBACK_HOST", "192.168.108.238"),
    )
    parser.add_argument(
        "--playback-port",
        type=int,
        default=int(os.getenv("PLAYBACK_PORT", "9996")),
    )
    parser.add_argument(
        "--playback-duration",
        type=int,
        default=int(os.getenv("PLAYBACK_DURATION", "30")),
        help="默认回放时长（秒）",
    )
    
    # 服务参数
    parser.add_argument("--tz", type=str, default=os.getenv("TZ", "Asia/Shanghai"))
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=int(os.getenv("MAX_ITERATIONS", "10")),
        help="Agent 最大迭代次数",
    )
    parser.add_argument(
        "--tracklet-limit",
        type=int,
        default=int(os.getenv("TRACKLET_LIMIT", "100")),
    )
    parser.add_argument(
        "--anomaly-limit",
        type=int,
        default=int(os.getenv("ANOMALY_LIMIT", "100")),
    )
    parser.add_argument(
        "--report-limit",
        type=int,
        default=int(os.getenv("REPORT_LIMIT", "50")),
    )
    
    args = parser.parse_args()
    
    # 检查 API Key
    if not args.openrouter_api_key:
        print("错误: 未提供 OpenRouter API Key")
        print("请通过 --openrouter-api-key 参数或 OPENROUTER_API_KEY 环境变量设置")
        sys.exit(1)
    
    # 创建配置
    db_cfg = DbConfig(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_password,
        database=args.db_name,
        schema=args.db_schema,
    )
    
    openrouter_cfg = OpenRouterConfig(
        api_key=args.openrouter_api_key,
        model=args.openrouter_model,
        max_tokens=args.openrouter_max_tokens,
        temperature=args.openrouter_temperature,
    )
    
    playback_cfg = PlaybackConfig(
        host=args.playback_host,
        port=args.playback_port,
        default_duration=args.playback_duration,
    )
    
    svc_cfg = ServiceConfig(
        tz=args.tz,
        max_iterations=args.max_iterations,
        tracklet_limit=args.tracklet_limit,
        anomaly_limit=args.anomaly_limit,
        report_limit=args.report_limit,
    )
    
    # 创建数据库引擎
    print(f"连接数据库: {args.db_host}:{args.db_port}/{args.db_name}")
    engine = create_pg_engine(db_cfg)
    
    # 创建 Flask 应用
    print(f"使用 OpenRouter 模型: {args.openrouter_model}")
    app = create_app(
        engine=engine,
        db_cfg=db_cfg,
        openrouter_cfg=openrouter_cfg,
        playback_cfg=playback_cfg,
        svc_cfg=svc_cfg,
    )
    
    # 启动服务
    print(f"启动 LLM API Service 在 http://{args.host}:{args.port}")
    print("API 端点:")
    print(f"  POST /chat          - 文本问答")
    print(f"  POST /chat_with_image - 带图片问答")
    print(f"  GET  /tools         - 列出可用工具")
    print(f"  GET  /health        - 健康检查")
    print("-" * 50)
    
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()

