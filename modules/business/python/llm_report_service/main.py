from __future__ import annotations


import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_report_service.config import DbConfig, ModelConfig, ServiceConfig
from llm_report_service.db.media_repo import get_media_asset_by_id
from llm_report_service.db.report_repo import ReportPublisher, REPORT_TYPE
from llm_report_service.service.episode_builder import EpisodeSemanticInput
from video_analysis.business_client import BusinessClient
from sqlalchemy import text
from llm_report_service.db.session import create_pg_engine
from ai_infra.factory import build_chat_model
from llm_report_service.service.report_runner import run_llm_report


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--llm-backend",
        choices=("sglang", "vllm"),
        default=ModelConfig.backend,
    )
    parser.add_argument("--llm-base-url", type=str, default=ModelConfig.base_url)
    parser.add_argument("--llm-model", type=str, default=ModelConfig.model_name)
    parser.add_argument("--llm-api-key", type=str, default=ModelConfig.api_key)
    parser.add_argument(
        "--llm-connect-timeout-s",
        type=float,
        default=ModelConfig.connect_timeout_s,
    )
    parser.add_argument(
        "--llm-request-timeout-s",
        type=float,
        default=ModelConfig.request_timeout_s,
    )
    parser.add_argument(
        "--llm-max-retries",
        type=int,
        default=ModelConfig.max_retries,
    )
    parser.add_argument("--max-new-tokens", type=int, default=1024)

    parser.add_argument("--db-host", type=str, default=os.getenv("DB_HOST"))
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-user", type=str, default=os.getenv("DB_USER"))
    parser.add_argument("--db-password", type=str, default=os.getenv("DB_PASSWORD"))
    parser.add_argument("--db-name", type=str, default=os.getenv("DB_NAME"))
    parser.add_argument("--db-schema", type=str, default="public")
    parser.add_argument("--scan-interval-s", type=float, default=60.0)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--media-limit", type=int, default=2)
    parser.add_argument("--max-video-frames", type=int, default=8)
    parser.add_argument("--media-base-dir", type=str, default="/home/guest/Documents/lkh/mtx/mediamtx")
    parser.add_argument(
        "--backfill-existing",
        action="store_true",
        help="显式补跑全部历史缺失报告；默认只处理近期和启动后的事件",
    )
    parser.add_argument(
        "--recent-pending-hours",
        type=float,
        default=1.0,
        help="非全量补跑模式下，重试该时间范围内缺失的报告，默认 1 小时",
    )

    args = parser.parse_args()

    for name in ("db_host", "db_user", "db_password", "db_name"):
        if not getattr(args, name):
            parser.error("缺少显式数据库配置：" + name)

    db_cfg = DbConfig(
        host=args.db_host,
        port=int(args.db_port),
        user=args.db_user,
        password=args.db_password,
        database=args.db_name,
        schema=args.db_schema,
    )

    model_cfg = ModelConfig(
        backend=args.llm_backend,
        base_url=args.llm_base_url,
        model_name=args.llm_model,
        api_key=args.llm_api_key,
        connect_timeout_s=float(args.llm_connect_timeout_s),
        request_timeout_s=float(args.llm_request_timeout_s),
        max_retries=int(args.llm_max_retries),
        max_new_tokens=(
            int(args.max_new_tokens)
            if args.max_new_tokens is not None
            else ModelConfig.max_new_tokens
        ),
    )

    svc_cfg = ServiceConfig(
        scan_interval_s=float(args.scan_interval_s),
        batch_size=int(args.batch_size),
        media_limit=int(args.media_limit),
        max_video_frames=int(args.max_video_frames),
        media_base_dir=str(args.media_base_dir),
    )

    engine = create_pg_engine(db_cfg)
    llm = build_chat_model(model_cfg)
    print(
        f"llm_backend={model_cfg.backend} "
        f"llm_model={model_cfg.model_name} "
        f"llm_base_url={model_cfg.base_url}"
    )

    client = BusinessClient(os.environ['CAPABILITY_BUSINESS_URL'],
        service_id=os.environ['CAPABILITY_SERVICE_ID'],
        token_provider=lambda: os.environ['CAPABILITY_SERVICE_TOKEN'], timeout=30)
    state_dir = Path(os.environ['REPORT_RUNTIME_DIR'])
    publisher = ReportPublisher(client, state_dir, model_cfg.model_name)
    if args.recent_pending_hours < 0:
        parser.error('--recent-pending-hours 必须非负')

    def generate(kind, subject_id):
        prior = publisher.load(kind, subject_id)
        if prior is not None:
            return publisher.publish(kind, subject_id, None, None, [])
        subject = client.get('/' + ('activities' if kind == 'activity' else 'events') + '/' + subject_id)
        evidence = subject.get('evidence', [])
        media = [get_media_asset_by_id(engine, db_cfg.schema, item['asset_id'])
                 for item in evidence if item.get('asset_id')]
        media = [item for item in media if item is not None][:svc_cfg.media_limit]
        semantic = EpisodeSemanticInput(episode_id=subject_id,
            time_range={'start': subject.get('start_ts', subject.get('start_at')),
                        'end': subject.get('end_ts', subject.get('end_at'))},
            camera_id=None, person={'business_subject': subject},
            trajectory={'tracks': subject.get('tracks', [])}, media=[])
        document, report_text = run_llm_report(llm, semantic, media, svc_cfg)
        return publisher.publish(kind, subject_id, document, report_text,
                                 [item['evidence_id'] for item in evidence])

    try:
        while True:
            # Finish uncertain deliveries before selecting new subjects. Never regenerate
            # a model response or change the request body after a lost acknowledgement.
            if state_dir.exists():
                for path in state_dir.glob('*.json'):
                    work = json.loads(path.read_text())
                    if not work.get('done'):
                        publisher.publish(work['kind'], work['subject_id'], None, None, [])
            cutoff = datetime.min.replace(tzinfo=timezone.utc) if args.backfill_existing else recent_cutoff(args.recent_pending_hours)
            with engine.connect() as conn:
                subjects = conn.execute(text("""
                    WITH subjects AS (
                      SELECT 'activity' AS kind,id,start_ts AS started_at FROM public.episode
                      WHERE identity_id IS NOT NULL AND state IN ('closed','interrupted') AND expires_at>now()
                      UNION ALL
                      SELECT 'event',id,start_at FROM public.business_event
                      WHERE event_type IN ('fire','behavior.fire') AND state IN ('closed','interrupted') AND expires_at>now()
                    )
                    SELECT kind,id::text FROM subjects s WHERE started_at>=:cutoff
                    AND NOT EXISTS (SELECT 1 FROM public.llm_report r
                      WHERE r.subject_kind=s.kind AND r.subject_id=s.id
                        AND r.report_type=:report_type AND r.expires_at>now())
                    ORDER BY started_at,id LIMIT :limit
                """), {'cutoff': cutoff, 'report_type': REPORT_TYPE, 'limit': svc_cfg.batch_size}).mappings().all()
            for item in subjects:
                generate(item['kind'], item['id'])
                print('已登记业务报告 subject=' + item['id'], flush=True)
            time.sleep(svc_cfg.scan_interval_s)
    finally:
        engine.dispose()


def recent_cutoff(hours):
    return datetime.now(timezone.utc) - timedelta(hours=float(hours))


if __name__ == '__main__':
    main()
