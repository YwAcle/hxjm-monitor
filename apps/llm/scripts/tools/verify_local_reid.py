"""只读登记库并验证 CLIP-ReID 图片检索，无需聊天模型。"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "modules/business/python"))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "modules/ai-infra/python"))
from business_api.config import DbConfig
from business_api.database import create_pg_engine
from business_api.gallery_repo import list_gallery
from business_api.gallery_search import GallerySearchService
from business_api.clipreid_client import ClipReIDClient
from business_api.text_reid_client import TextReIDClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, help="查询图片，省略则用第一张有效登记图片作自身检索")
    args = parser.parse_args()
    cfg = DbConfig(host=os.getenv("DB_HOST", "100.127.237.7"), port=int(os.getenv("DB_PORT", "5432")),
                   user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", ""),
                   database=os.getenv("DB_NAME", "postgres"), schema=os.getenv("DB_SCHEMA", "public"))
    engine = create_pg_engine(cfg)
    try:
        rows = list_gallery(engine, cfg.schema, 2001)
        if not rows:
            raise ValueError("登记库为空")
        query = base64.b64encode(args.image.read_bytes()).decode() if args.image else rows[0].image_base64
        service = GallerySearchService(
            engine=engine, schema=cfg.schema,
            feature_client=ClipReIDClient(
                os.getenv("REID_FEATURE_BASE_URL", "http://100.127.237.7:28024"),
                float(os.getenv("REID_TIMEOUT_S", "30")), os.getenv("REID_FEATURE_SPACE_ID", ""),
            ),
            text_feature_client=TextReIDClient(
                os.getenv("REID_FEATURE_BASE_URL", "http://100.127.237.7:28024"),
                float(os.getenv("REID_TIMEOUT_S", "30")),
                os.getenv("REID_TEXT_FEATURE_SPACE_ID", ""),
                os.getenv("REID_TEXT_CONTRACT_ID", ""),
                int(os.getenv("REID_TEXT_MAX_CHARS", "200")),
            ),
        )
        start = monotonic()
        result = service.search_image(query, 5)
        for candidate in result["candidates"]:
            candidate.pop("image_base64", None)
        result["elapsed_seconds"] = round(monotonic() - start, 3)
        if not args.image:
            result["self_top1"] = bool(result["candidates"] and result["candidates"][0]["person_id"] == rows[0].id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["status"] != "ok" or (not args.image and not result["self_top1"]):
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
