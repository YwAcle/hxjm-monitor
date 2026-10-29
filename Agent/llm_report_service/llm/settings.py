"""Shared model settings used by every Python service in this repository."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
from urllib.parse import urlsplit

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file() -> None:
    env_file = REPOSITORY_ROOT / ".env"
    if not env_file.is_file():
        return

    try:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
        return
    except ImportError:
        pass

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key.replace("_", "").isalnum() or key[0].isdigit():
            continue
        if key not in os.environ:
            tokens = shlex.split(value, comments=True, posix=True)
            os.environ[key] = " ".join(tokens)


def resolve_model_settings(env: dict, root: Path = REPOSITORY_ROOT) -> dict[str, str]:
    """Shell 和 Python 共用配置；独立保留本地/API 配置，兼容旧公共字段。"""
    mode = env.get("LLM_MODE", "local").strip().lower()
    if mode not in {"local", "api"}:
        raise ValueError("LLM_MODE 必须为 local 或 api")
    backend = env.get("LLM_BACKEND", "sglang").strip().lower()
    if backend not in {"vllm", "sglang"}:
        raise ValueError("LLM_BACKEND 必须为 vllm 或 sglang")
    prefix = backend.upper()
    model_path = env.get("LLM_MODEL_PATH") or env.get(f"{prefix}_MODEL_PATH") or str(root / "InternVL3_5-8B")
    if model_path.startswith("."):
        model_path = str((root / model_path).resolve())
    port = env.get("LLM_SERVER_PORT") or env.get(f"{prefix}_PORT") or "8000"
    local = {
        "MODEL_ID": env.get("LLM_LOCAL_MODEL_ID") or env.get("LLM_MODEL_ID") or env.get(f"{prefix}_MODEL_NAME") or Path(model_path.rstrip("/")).name,
        "BASE_URL": env.get("LLM_LOCAL_BASE_URL") or env.get("LLM_BASE_URL") or f"http://127.0.0.1:{port}/v1",
        "API_KEY": env.get("LLM_LOCAL_API_KEY", env.get("LLM_API_KEY", "unused")),
        "ENABLE_THINKING": env.get("LLM_LOCAL_ENABLE_THINKING", env.get("LLM_ENABLE_THINKING", "")),
    }
    settings = {
        "LLM_MODE": mode,
        "LLM_BACKEND": backend,
        "LLM_MODEL_PATH": model_path,
        "LLM_SERVER_HOST": env.get("LLM_SERVER_HOST") or env.get(f"{prefix}_HOST") or "127.0.0.1",
        "LLM_SERVER_PORT": port,
        # API 模式归一化公共字段前保存本地值，供子进程及后续切回本地使用。
        **{f"LLM_LOCAL_{key}": value for key, value in local.items()
           if mode == "api" or f"LLM_LOCAL_{key}" in env},
    }
    if mode == "api":
        # 不回退到本地地址/模型/密钥，避免 API 配置不完整时误用本地服务。
        remote = {
            "BASE_URL": env.get("LLM_REMOTE_BASE_URL", "").strip().rstrip("/"),
            "MODEL_ID": env.get("LLM_REMOTE_MODEL_ID", "").strip(),
            "API_KEY": env.get("LLM_REMOTE_API_KEY", ""),
            "ENABLE_THINKING": env.get("LLM_REMOTE_ENABLE_THINKING", ""),
        }
        for key in ("BASE_URL", "MODEL_ID"):
            if not remote[key]:
                raise ValueError(f"API 模式需要配置 LLM_REMOTE_{key}")
        url = urlsplit(remote["BASE_URL"])
        if url.scheme not in {"http", "https"} or not url.hostname:
            raise ValueError("LLM_REMOTE_BASE_URL 必须为 http(s) 接口根地址")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("LLM_REMOTE_BASE_URL 不支持内嵌凭据、查询参数或片段；密钥请使用 LLM_REMOTE_API_KEY")
        if url.path.endswith(("/chat/completions", "/responses")):
            raise ValueError("LLM_REMOTE_BASE_URL 应为接口根地址，不要包含 /chat/completions 或 /responses")
        active = remote
    else:
        active = local
    settings.update({f"LLM_{key}": value for key, value in active.items()})
    healthcheck = env.get("LLM_HEALTHCHECK", "auto").strip().lower()
    if healthcheck not in {"auto", "models", "none"}:
        raise ValueError("LLM_HEALTHCHECK 必须为 auto、models 或 none")
    settings["LLM_HEALTHCHECK"] = healthcheck
    response_format = "json_schema"
    if mode == "api":
        response_format = env.get("LLM_REMOTE_RESPONSE_FORMAT", "json_schema").strip().lower()
        if response_format not in {"json_schema", "json_object", "none"}:
            raise ValueError("LLM_REMOTE_RESPONSE_FORMAT 必须为 json_schema、json_object 或 none")
    settings["LLM_RESPONSE_FORMAT"] = response_format
    # 旧部署仍可使用后端专属项；新配置只需公共项。
    shared = {
        "LLM_TP_SIZE": (f"{prefix}_TP_SIZE", "1"),
        "LLM_CONTEXT_LENGTH": ("VLLM_MAX_MODEL_LEN" if backend == "vllm" else "SGLANG_CONTEXT_LENGTH", "14588"),
        "LLM_GPU_MEMORY_UTILIZATION": ("VLLM_GPU_MEMORY_UTILIZATION" if backend == "vllm" else "SGLANG_MEM_FRACTION_STATIC", "0.80"),
        "LLM_CHAT_TEMPLATE": (f"{prefix}_CHAT_TEMPLATE", ""),
        "LLM_DTYPE": (f"{prefix}_DTYPE", "bfloat16"),
    }
    for key, (legacy, default) in shared.items():
        settings[key] = env.get(key) or env.get(legacy) or default
    template = settings["LLM_CHAT_TEMPLATE"]
    if template.startswith("."):
        settings["LLM_CHAT_TEMPLATE"] = str((root / template).resolve())
    if any("\n" in value or "\r" in value for value in settings.values()):
        raise ValueError("模型配置值不能包含换行")
    return settings


_load_env_file()
os.environ.update(resolve_model_settings(os.environ))

LLM_MODE = os.getenv("LLM_MODE", "local")
LLM_BACKEND = os.getenv("LLM_BACKEND", "sglang").strip().lower()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "internvl3.5-8b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "unused")
LLM_HEALTHCHECK = os.getenv("LLM_HEALTHCHECK", "models")
LLM_RESPONSE_FORMAT = os.getenv("LLM_RESPONSE_FORMAT", "json_schema")
LLM_CONNECT_TIMEOUT_S = float(os.getenv("LLM_CONNECT_TIMEOUT_S", "5"))
LLM_REQUEST_TIMEOUT_S = float(os.getenv("LLM_REQUEST_TIMEOUT_S", "180"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))


def _optional_bool_env(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} 必须为 true 或 false，实际为 {value!r}")


LLM_ENABLE_THINKING = _optional_bool_env("LLM_ENABLE_THINKING")
