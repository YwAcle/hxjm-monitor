"""输出归一化模型配置；默认隐藏密钥，--shell 仅供 load_env.sh 内部使用。"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm_report_service.llm.settings import resolve_model_settings

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--shell", action="store_true", help=argparse.SUPPRESS)
args = parser.parse_args()
for key, value in resolve_model_settings(os.environ).items():
    if key.endswith("_API_KEY") and not args.shell:
        continue
    print(f"{key}={value}")
