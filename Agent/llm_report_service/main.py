from __future__ import annotations


import argparse
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_report_service.config import DbConfig, ModelConfig, ServiceConfig
from llm_report_service.db.episode_repo import (
    count_episodes,
    fetch_episode_batch,
    fetch_pending_episodes,
    fetch_primary_tracklet,
)
from llm_report_service.db.media_repo import get_media_asset_by_id, select_episode_media
from llm_report_service.db.report_repo import has_llm_report, save_llm_report
from llm_report_service.db.session import create_pg_engine
from llm_report_service.db.stranger_repo import get_stranger_code
from llm_report_service.db.vad_repo import count_vads, fetch_pending_vads, fetch_vad_batch
from llm_report_service.llm.factory import build_chat_model
from llm_report_service.service.episode_builder import (
    build_episode_semantic_input,
    build_vad_semantic_input,
)
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

    parser.add_argument("--db-host", type=str, default="100.127.237.7")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-user", type=str, default="root")
    parser.add_argument("--db-password", type=str, default="123456")
    parser.add_argument("--db-name", type=str, default="postgres")
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

    prompt_type_reid = "reid"
    prompt_type_vad = "vad"

    if args.recent_pending_hours < 0:
        parser.error("--recent-pending-hours 必须大于或等于 0")

    # 计算近期时间起始时间
    def recent_cutoff() -> datetime:
        return datetime.now(timezone.utc) - timedelta(hours=float(args.recent_pending_hours))

    # 是否允许处理事件
    def should_process(event_ts: datetime) -> bool:
        return args.backfill_existing or event_ts >= recent_cutoff()

    # 处理单个事件
    def process_one_episode(ep):
        if not should_process(ep.start_ts):
            print(f"skip historical episode={ep.id} start_ts={ep.start_ts.isoformat()}")
            return
        if has_llm_report(engine, db_cfg.schema, prompt_type=prompt_type_reid, episode_id=ep.id):
            return

        tracklet = fetch_primary_tracklet(engine, db_cfg.schema, ep.id)
        stream_id = tracklet.stream_id if tracklet is not None else None

        override_person_name = None
        meta = ep.meta if isinstance(ep.meta, dict) else None
        stranger_target_id = None
        if meta is not None:
            stranger_target_id = meta.get("stranger_target_id")
        if stranger_target_id is None and tracklet is not None:
            stranger_target_id = tracklet.stranger_target_id

        if stranger_target_id is not None:
            code = get_stranger_code(engine, db_cfg.schema, str(stranger_target_id))
            if code is not None and code.strip() != "":
                code = code.strip()
                if code.upper().startswith("STR-"):
                    override_person_name = code
                elif code.isdigit():
                    override_person_name = f"STR-{int(code):03d}"
                else:
                    override_person_name = f"STR-{code}"

        media_assets = select_episode_media(
            engine=engine,
            schema=db_cfg.schema,
            episode_id=ep.id,
            stream_id=stream_id,
            start_ts=ep.start_ts,
            end_ts=ep.end_ts,
            limit=svc_cfg.media_limit,
        )

        media_sem = [
            {
                "type": "video",
                "path": m.path,
                "start_ts": m.start_ts.isoformat(),
                "duration_ms": m.duration_ms,
                "asset_type": m.asset_type,
            }
            for m in media_assets
        ]

        semantic = build_episode_semantic_input(ep, tracklet, media_sem, override_person_name=override_person_name)
        report_json, report_text = run_llm_report(llm, semantic, media_assets, svc_cfg)

        _ = save_llm_report(
            engine=engine,
            schema=db_cfg.schema,
            prompt_type=prompt_type_reid,
            episode_id=ep.id,
            report_json=report_json,
            report_text=report_text,
        )

        print(f"saved llm_report for episode={ep.id}")

    def process_one_vad(vad):
        if not should_process(vad.created_at):
            print(f"skip historical vad={vad.id} created_at={vad.created_at.isoformat()}")
            return
        if has_llm_report(engine, db_cfg.schema, prompt_type=prompt_type_vad, vad_id=vad.id):
            return

        media_asset = get_media_asset_by_id(engine, db_cfg.schema, vad.media_asset_id)
        media_assets = [media_asset] if media_asset is not None else []
        media_sem = (
            [
                {
                    "type": "video",
                    "path": media_asset.path,
                    "start_ts": media_asset.start_ts.isoformat(),
                    "duration_ms": media_asset.duration_ms,
                    "asset_type": media_asset.asset_type,
                }
            ]
            if media_asset is not None
            else []
        )

        semantic = build_vad_semantic_input(vad, media_asset, media_sem)
        report_json, report_text = run_llm_report(llm, semantic, media_assets, svc_cfg)

        _ = save_llm_report(
            engine=engine,
            schema=db_cfg.schema,
            prompt_type=prompt_type_vad,
            vad_id=vad.id,
            report_json=report_json,
            report_text=report_text,
        )

        print(f"saved llm_report for vad={vad.id}")

    last_total = count_episodes(engine, db_cfg.schema)
    print(f"episode_total={last_total}")

    last_vad_total = count_vads(engine, db_cfg.schema)
    print(f"vad_total={last_vad_total}")

    if args.backfill_existing:
        print("backfill mode enabled: processing all historical missing reports")
        while True:
            pending_vads = fetch_pending_vads(
                engine=engine,
                schema=db_cfg.schema,
                prompt_type=prompt_type_vad,
                limit=svc_cfg.batch_size,
            )
            if len(pending_vads) == 0:
                break

            for v in pending_vads:
                try:
                    process_one_vad(v)
                except Exception:
                    print(f"failed vad={v.id}")
                    traceback.print_exc()

        while True:
            pending = fetch_pending_episodes(
                engine=engine,
                schema=db_cfg.schema,
                prompt_type=prompt_type_reid,
                limit=svc_cfg.batch_size,
            )
            if len(pending) == 0:
                break

            for ep in pending:
                try:
                    process_one_episode(ep)
                except Exception:
                    print(f"failed episode={ep.id}")
                    traceback.print_exc()

    vad_scan_interval_s = 10.0
    next_episode_scan_at = time.monotonic() + float(svc_cfg.scan_interval_s)

    while True:
        time.sleep(vad_scan_interval_s)

        new_vad_total = count_vads(engine, db_cfg.schema)
        if new_vad_total > last_vad_total:
            print(f"vad_total_grew {last_vad_total} -> {new_vad_total}")
            offset = last_vad_total
            while offset < new_vad_total:
                batch = fetch_vad_batch(
                    engine,
                    db_cfg.schema,
                    offset=offset,
                    limit=svc_cfg.batch_size,
                )
                if len(batch) == 0:
                    break
                for v in batch:
                    try:
                        process_one_vad(v)
                    except Exception:
                        print(f"failed vad={v.id}")
                        traceback.print_exc()

                offset += len(batch)

            last_vad_total = new_vad_total

        pending_vads = fetch_pending_vads(
            engine=engine,
            schema=db_cfg.schema,
            prompt_type=prompt_type_vad,
            limit=svc_cfg.batch_size,
            since_ts=recent_cutoff(),
        )
        for v in pending_vads:
            try:
                process_one_vad(v)
            except Exception:
                print(f"failed vad={v.id}")
                traceback.print_exc()

        if time.monotonic() < next_episode_scan_at:
            continue
        next_episode_scan_at = time.monotonic() + float(svc_cfg.scan_interval_s)

        new_total = count_episodes(engine, db_cfg.schema)
        if new_total > last_total:
            print(f"episode_total_grew {last_total} -> {new_total}")
            offset = last_total
            while offset < new_total:
                batch = fetch_episode_batch(
                    engine,
                    db_cfg.schema,
                    offset=offset,
                    limit=svc_cfg.batch_size,
                )
                if len(batch) == 0:
                    break
                for ep in batch:
                    try:
                        process_one_episode(ep)
                    except Exception:
                        print(f"failed episode={ep.id}")
                        traceback.print_exc()

                offset += len(batch)

            last_total = new_total

        # 兜底：补跑未生成 report 的 episode（避免乱序插入导致的漏处理）
        pending = fetch_pending_episodes(
            engine=engine,
            schema=db_cfg.schema,
            prompt_type=prompt_type_reid,
            limit=svc_cfg.batch_size,
            since_ts=recent_cutoff(),
        )
        for ep in pending:
            try:
                process_one_episode(ep)
            except Exception:
                print(f"failed episode={ep.id}")
                traceback.print_exc()


if __name__ == "__main__":
    main()
