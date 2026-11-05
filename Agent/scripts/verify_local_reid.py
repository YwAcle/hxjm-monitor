"""只读验证新轨迹身份检索，不写数据库、不启动服务。

省略 --image 时直接取一条历史特征做数据库自检：同一条特征应检索到它所属的身份。
提供 --image 时通过 CLIP-ReID 编码查询图，再检索 feature 表并返回真实轨迹记录。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm_agent_service.config import DbConfig
from llm_agent_service.db.session import create_pg_engine
from llm_agent_service.db.identity_repo import (
    count_searchable_features,
    default_feature_space,
    sample_feature,
    search_identities,
)
from llm_agent_service.service.gallery_search import GallerySearchService
from llm_agent_service.service.clipreid_client import ClipReIDClient
from llm_agent_service.service.text_reid_client import TextReIDClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, help="查询图片；省略时用第一条历史特征做数据库自检")
    parser.add_argument("--feature-space-id", default=os.getenv("REID_FEATURE_SPACE_ID", ""),
                        help="数据库特征空间；省略时取第一个启用的空间")
    parser.add_argument("--expect-identity-id", default="",
                        help="可选：要求该身份出现在第一名")
    args = parser.parse_args()
    cfg = DbConfig(host=os.getenv("DB_HOST", "100.127.237.7"), port=int(os.getenv("DB_PORT", "5432")),
                   user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", "123456"),
                   database=os.getenv("DB_NAME", "postgres"), schema=os.getenv("DB_SCHEMA", "public"))
    base_url = os.getenv("REID_FEATURE_BASE_URL", "http://100.127.237.7:28024")
    timeout = float(os.getenv("REID_TIMEOUT_S", "30"))
    engine = create_pg_engine(cfg)
    try:
        space = args.feature_space_id or default_feature_space(engine, cfg.schema)
        if not space:
            raise ValueError("数据库没有启用的特征空间")
        start = monotonic()
        if args.image:
            service = GallerySearchService(
                engine=engine, schema=cfg.schema,
                feature_client=ClipReIDClient(
                    base_url, timeout, os.getenv("REID_FEATURE_SPACE_ID", "")),
                text_feature_client=TextReIDClient(
                    base_url, timeout,
                    os.getenv("REID_TEXT_FEATURE_SPACE_ID", ""),
                    os.getenv("REID_TEXT_CONTRACT_ID", ""),
                    int(os.getenv("REID_TEXT_MAX_CHARS", "200")),
                ),
            )
            query = base64.b64encode(args.image.read_bytes()).decode()
            result = service.search_image(query, 5)
        else:
            feature = sample_feature(engine, cfg.schema, space)
            if feature is None:
                raise ValueError("特征空间中没有可检索的历史轨迹特征")
            expected = feature["assignment_identity_id"] or feature["feature_identity_id"]
            candidates = search_identities(
                engine, cfg.schema, space, feature["embedding"], 5)
            result = {
                "type": "pedestrian_search", "search_type": "database_self_check",
                "status": "ok" if candidates else "no_identity_candidates",
                "scope": "identity_history", "method": "stored_feature",
                "embedding_model": space,
                "scanned_count": count_searchable_features(engine, cfg.schema, space),
                "compatible_count": candidates[0].compatible_count if candidates else 0,
                "count": len(candidates),
                "candidates": [asdict(item) for item in candidates],
                "self_top1": bool(candidates and candidates[0].identity_id == expected),
            }
        result["elapsed_seconds"] = round(monotonic() - start, 3)
        if args.expect_identity_id:
            result["expected_identity_top1"] = bool(
                result["candidates"]
                and result["candidates"][0]["identity_id"] == args.expect_identity_id)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        if result["status"] != "ok" or result.get("self_top1") is False:
            raise SystemExit(1)
        if result.get("expected_identity_top1") is False:
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()