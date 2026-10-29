from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_chat_service.app import create_app
from llm_chat_service.config import DbConfig, ModelConfig, ServiceConfig
from llm_chat_service.db.session import create_pg_engine
from llm_chat_service.llm.model import build_llm


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)

    parser.add_argument("--llm-base-url", type=str, default=os.getenv("LLM_BASE_URL", ModelConfig.base_url))
    parser.add_argument("--llm-model", type=str, default=os.getenv("LLM_MODEL_ID", ModelConfig.model_name))
    parser.add_argument("--llm-api-key", type=str, default=os.getenv("LLM_API_KEY", ModelConfig.api_key))
    parser.add_argument("--llm-connect-timeout-s", type=float, default=ModelConfig.connect_timeout_s)
    parser.add_argument("--llm-request-timeout-s", type=float, default=ModelConfig.request_timeout_s)
    parser.add_argument("--llm-max-retries", type=int, default=ModelConfig.max_retries)
    parser.add_argument("--max-new-tokens", type=int, default=1024)

    parser.add_argument("--db-host", type=str, default="192.168.108.238")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-user", type=str, default="root")
    parser.add_argument("--db-password", type=str, default="123456")
    parser.add_argument("--db-name", type=str, default="postgres")
    parser.add_argument("--db-schema", type=str, default="public")

    parser.add_argument("--tz", type=str, default="Asia/Shanghai")
    parser.add_argument("--playback-base-url", type=str, default="")
    parser.add_argument("--media-base-dir", type=str, default="/home/guest/Documents/lkh/mtx/mediamtx")
    parser.add_argument("--playback-top-n", type=int, default=10)
    parser.add_argument("--tracklet-limit", type=int, default=200)
    parser.add_argument("--report-limit", type=int, default=200)
    parser.add_argument("--media-limit-per-episode", type=int, default=2)

    args = parser.parse_args()

    db_cfg = DbConfig(
        host=args.db_host,
        port=int(args.db_port),
        user=args.db_user,
        password=args.db_password,
        database=args.db_name,
        schema=args.db_schema,
    )

    model_cfg = ModelConfig(
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
        playback_top_n=int(args.playback_top_n),
        tracklet_limit=int(args.tracklet_limit),
        report_limit=int(args.report_limit),
        media_limit_per_episode=int(args.media_limit_per_episode),
        media_base_dir=str(args.media_base_dir),
        playback_base_url=str(args.playback_base_url),
    )

    engine = create_pg_engine(db_cfg)
    llm = build_llm(model_cfg)

    app = create_app(engine=engine, db_cfg=db_cfg, svc_cfg=svc_cfg, llm=llm)
    app.run(host=args.host, port=int(args.port), threaded=True)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
