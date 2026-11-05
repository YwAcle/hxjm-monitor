"""按策略检查模型列表：0就绪或已跳过、1不可用、2模型名不匹配。"""

import json
import os
import sys
import socket
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import URLError


def check_models(data, model):
    models = [item.get("id") for item in data.get("data", []) if isinstance(item, dict)]
    if model not in models:
        print(f"模型名称不匹配：配置为 {model!r}，接口实际提供 {models!r}。请检查 LLM_MODEL_PATH/LLM_MODEL_ID 并重启相关服务。", file=sys.stderr)
        return 2
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] in {"--port-open", "--agent-port-open"}:
        if sys.argv[1] == "--agent-port-open":
            host = os.getenv('AGENT_HOST', '127.0.0.1')
            if host in {'0.0.0.0', '::'}:
                host = '127.0.0.1'
            address = (host, int(os.getenv('AGENT_PORT', '8002')))
        else:
            url = urlsplit(os.environ["LLM_BASE_URL"])
            address = (url.hostname, url.port or (443 if url.scheme == "https" else 80))
        try:
            with socket.create_connection(address, timeout=2):
                return 0
        except OSError:
            return 1
    healthcheck = os.getenv("LLM_HEALTHCHECK", "auto")
    if healthcheck == "none" or (healthcheck == "auto" and os.getenv("LLM_MODE", "local") == "api"):
        print("已跳过 /models 检查；接口可用性与鉴权将在实际模型调用时验证。")
        return 0
    request = Request(os.environ["LLM_BASE_URL"].rstrip("/") + "/models",
                      headers={"Authorization": "Bearer " + os.getenv("LLM_API_KEY", "unused")})
    try:
        with build_opener(ProxyHandler({})).open(request, timeout=5) as response:
            data = json.load(response)
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            return 1
        return check_models(data, os.environ["LLM_MODEL_ID"])
    except (URLError, OSError, ValueError):
        return 1


if __name__ == "__main__":
    sys.exit(main())
