"""只读登记库并验证 Chinese-CLIP 文本→图像检索，无需聊天模型。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm_agent_service.config import DbConfig
from llm_agent_service.db.session import create_pg_engine
from llm_agent_service.service.clipreid_client import ClipReIDClient
from llm_agent_service.service.gallery_search import GallerySearchService
from llm_agent_service.service.text_reid_client import TextReIDClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--description", default="穿红色上衣的人", help="要检索的外观描述")
    parser.add_argument("--top-k", type=int, default=5, help="返回候选数，1~10")
    args = parser.parse_args()
    if not 1 <= args.top_k <= 10:
        parser.error("--top-k 必须在 1~10 之间")
    cfg = DbConfig(host=os.getenv("DB_HOST", "100.127.237.7"), port=int(os.getenv("DB_PORT", "5432")),
                   user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", "123456"),
                   database=os.getenv("DB_NAME", "postgres"), schema=os.getenv("DB_SCHEMA", "public"))
    base_url = os.getenv("REID_FEATURE_BASE_URL", "http://100.127.237.7:28024")
    timeout_s = float(os.getenv("REID_TIMEOUT_S", "30"))
    engine = create_pg_engine(cfg)
    try:
        service = GallerySearchService(
            engine=engine, schema=cfg.schema,
            feature_client=ClipReIDClient(base_url, timeout_s,
                                          os.getenv("REID_FEATURE_SPACE_ID", "")),
            text_feature_client=TextReIDClient(
                base_url, timeout_s,
                os.getenv("REID_TEXT_FEATURE_SPACE_ID", ""),
                os.getenv("REID_TEXT_CONTRACT_ID", ""),
                int(os.getenv("REID_TEXT_MAX_CHARS", "200")),
            ),
            text_max_chars=int(os.getenv("REID_TEXT_MAX_CHARS", "200")),
        )
        start = monotonic()
        result = service.search_description(args.description, args.top_k)
        for candidate in result["candidates"]:
            candidate.pop("image_base64", None)
        result["elapsed_seconds"] = round(monotonic() - start, 3)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["status"] != "ok":
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()