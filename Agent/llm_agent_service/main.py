"""纯 Agent 服务入口。"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_agent_service.app import create_app
from llm_agent_service.config import DbConfig, ModelConfig, ServiceConfig
from llm_agent_service.db.session import create_pg_engine
from llm_agent_service.llm import build_llm


def main():
    parser = argparse.ArgumentParser(description="智慧监控 Agent 服务")

    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8002)

    parser.add_argument(
        "--llm-backend",
        choices=("sglang", "vllm"),
        default=os.getenv("LLM_BACKEND", ModelConfig.backend),
    )
    parser.add_argument(
        "--llm-base-url",
        type=str,
        default=os.getenv("LLM_BASE_URL", ModelConfig.base_url),
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=os.getenv("LLM_MODEL_ID", ModelConfig.model_name),
    )
    parser.add_argument(
        "--llm-api-key",
        type=str,
        default=os.getenv("LLM_API_KEY", ModelConfig.api_key),
    )
    parser.add_argument(
        "--llm-connect-timeout-s",
        type=float,
        default=float(
            os.getenv("LLM_CONNECT_TIMEOUT_S", ModelConfig.connect_timeout_s)
        ),
    )
    parser.add_argument(
        "--llm-request-timeout-s",
        type=float,
        default=float(
            os.getenv("LLM_REQUEST_TIMEOUT_S", ModelConfig.request_timeout_s)
        ),
    )
    parser.add_argument(
        "--llm-max-retries",
        type=int,
        default=int(os.getenv("LLM_MAX_RETRIES", ModelConfig.max_retries)),
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=int(os.getenv("LLM_MAX_NEW_TOKENS", 512)),
    )
    parser.add_argument(
        "--agent-request-timeout-s",
        type=float,
        default=float(os.getenv("AGENT_REQUEST_TIMEOUT_S", "180")),
    )
    parser.add_argument(
        "--agent-answer-max-new-tokens",
        type=int,
        default=int(os.getenv("AGENT_ANSWER_MAX_NEW_TOKENS", "2048")),
    )

    parser.add_argument("--db-host", type=str, default=os.getenv("DB_HOST", "100.127.237.7"))
    parser.add_argument("--db-port", type=int, default=int(os.getenv("DB_PORT", "5432")))
    parser.add_argument("--db-user", type=str, default=os.getenv("DB_USER", "root"))
    parser.add_argument("--db-password", type=str, default=os.getenv("DB_PASSWORD", "123456"))
    parser.add_argument("--db-name", type=str, default=os.getenv("DB_NAME", "postgres"))
    parser.add_argument("--db-schema", type=str, default=os.getenv("DB_SCHEMA", "public"))
    parser.add_argument(
        "--db-connect-timeout-s",
        type=float,
        default=float(os.getenv("DB_CONNECT_TIMEOUT_S", "5")),
    )

    parser.add_argument("--tz", type=str, default=os.getenv("TZ_NAME", "Asia/Shanghai"))
    parser.add_argument(
        "--playback-base-url",
        type=str,
        default=os.getenv("PLAYBACK_BASE_URL", ""),
    )
    parser.add_argument(
        "--memory-max-sessions",
        type=int,
        default=int(os.getenv("MEMORY_MAX_SESSIONS", 1000)),
    )
    parser.add_argument(
        "--memory-max-messages",
        type=int,
        default=int(os.getenv("MEMORY_MAX_MESSAGES", 20)),
    )
    parser.add_argument(
        "--max-request-bytes",
        type=int,
        default=int(os.getenv("MAX_REQUEST_BYTES", 20 * 1024 * 1024)),
    )
    parser.add_argument(
        "--max-prompt-chars",
        type=int,
        default=int(os.getenv("MAX_PROMPT_CHARS", 8000)),
    )
    parser.add_argument(
        "--max-image-bytes",
        type=int,
        default=int(os.getenv("MAX_IMAGE_BYTES", 10 * 1024 * 1024)),
    )
    parser.add_argument(
        "--max-image-pixels",
        type=int,
        default=int(os.getenv("MAX_IMAGE_PIXELS", 25_000_000)),
    )
    parser.add_argument(
        "--max-image-side",
        type=int,
        default=int(os.getenv("MAX_IMAGE_SIDE", 8192)),
    )

    parser.add_argument("--reid-timeout-s", type=float, default=float(os.getenv("REID_TIMEOUT_S", "15")))
    parser.add_argument("--reid-feature-base-url", default=os.getenv("REID_FEATURE_BASE_URL", "http://100.127.237.7:28024"))
    parser.add_argument("--reid-feature-space-id", default=os.getenv("REID_FEATURE_SPACE_ID", ""))
    parser.add_argument("--reid-text-feature-space-id", default=os.getenv("REID_TEXT_FEATURE_SPACE_ID", ""))
    parser.add_argument("--reid-text-contract-id", default=os.getenv("REID_TEXT_CONTRACT_ID", ""))
    parser.add_argument("--reid-text-max-chars", type=int, default=int(os.getenv("REID_TEXT_MAX_CHARS", "200")))
    parser.add_argument(
        "--image-asset-ttl-s",
        type=int,
        default=int(os.getenv("IMAGE_ASSET_TTL_S", "1800")),
    )
    parser.add_argument(
        "--image-asset-max-per-session",
        type=int,
        default=int(os.getenv("IMAGE_ASSET_MAX_PER_SESSION", "4")),
    )
    parser.add_argument(
        "--image-asset-max-bytes-per-session",
        type=int,
        default=int(os.getenv("IMAGE_ASSET_MAX_BYTES_PER_SESSION", str(32 * 1024 * 1024))),
    )
    parser.add_argument(
        "--image-asset-max-total-bytes",
        type=int,
        default=int(os.getenv("IMAGE_ASSET_MAX_TOTAL_BYTES", str(256 * 1024 * 1024))),
    )
    args = parser.parse_args()
    if args.reid_timeout_s <= 0:
        parser.error("--reid-timeout-s 必须大于 0")
    if args.reid_text_max_chars <= 0:
        parser.error("--reid-text-max-chars 必须大于 0")
    if args.agent_request_timeout_s <= 0:
        parser.error("--agent-request-timeout-s 必须大于 0")
    if args.agent_answer_max_new_tokens <= 0:
        parser.error("--agent-answer-max-new-tokens 必须大于 0")
    for flag, value in (
        ("--image-asset-ttl-s", args.image_asset_ttl_s),
        ("--image-asset-max-per-session", args.image_asset_max_per_session),
        ("--image-asset-max-bytes-per-session", args.image_asset_max_bytes_per_session),
        ("--image-asset-max-total-bytes", args.image_asset_max_total_bytes),
    ):
        if value <= 0:
            parser.error(f"{flag} 必须大于 0")

    db_cfg = DbConfig(
        host=args.db_host,
        port=int(args.db_port),
        user=args.db_user,
        password=args.db_password,
        database=args.db_name,
        schema=args.db_schema,
        connect_timeout_s=float(args.db_connect_timeout_s),
    )

    model_cfg = ModelConfig(
        backend=args.llm_backend,
        base_url=args.llm_base_url,
        model_name=args.llm_model,
        api_key=args.llm_api_key,
        connect_timeout_s=float(args.llm_connect_timeout_s),
        request_timeout_s=float(args.llm_request_timeout_s),
        max_retries=int(args.llm_max_retries),
        max_new_tokens=int(args.max_new_tokens),
    )

    svc_cfg = ServiceConfig(
        tz=args.tz,
        playback_base_url=str(args.playback_base_url),
        memory_max_sessions=int(args.memory_max_sessions),
        memory_max_messages=int(args.memory_max_messages),
        max_request_bytes=int(args.max_request_bytes),
        max_prompt_chars=int(args.max_prompt_chars),
        max_image_bytes=int(args.max_image_bytes),
        max_image_pixels=int(args.max_image_pixels),
        max_image_side=int(args.max_image_side),
        reid_timeout_s=args.reid_timeout_s,
        reid_feature_base_url=args.reid_feature_base_url,
        reid_feature_space_id=args.reid_feature_space_id,
        reid_text_feature_space_id=args.reid_text_feature_space_id,
        reid_text_contract_id=args.reid_text_contract_id,
        reid_text_max_chars=args.reid_text_max_chars,
        agent_request_timeout_s=args.agent_request_timeout_s,
        agent_answer_max_new_tokens=args.agent_answer_max_new_tokens,
        image_asset_ttl_s=args.image_asset_ttl_s,
        image_asset_max_per_session=args.image_asset_max_per_session,
        image_asset_max_bytes_per_session=args.image_asset_max_bytes_per_session,
        image_asset_max_total_bytes=args.image_asset_max_total_bytes,
    )

    engine = create_pg_engine(db_cfg)
    llm = build_llm(model_cfg)
    print(
        f"llm_backend={model_cfg.backend} "
        f"llm_model={model_cfg.model_name} "
        f"llm_base_url={model_cfg.base_url}"
    )
    print(
        f"db_endpoint={db_cfg.host}:{db_cfg.port} "
        f"db_name={db_cfg.database} db_schema={db_cfg.schema}"
    )

    app = create_app(engine=engine, db_cfg=db_cfg, svc_cfg=svc_cfg, llm=llm)
    print(f"启动智慧监控 Agent 服务：http://{args.host}:{args.port}")
    app.run(host=args.host, port=int(args.port), threaded=True)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
