"""Download pinned MediaMTX and, on Windows, an FFmpeg binary. No admin needed.

Only .runtime/ is written; binaries aren't bundled in the source ZIP.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import tarfile
import time
import urllib.request
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
VERSION = "v1.12.3"


def fetch(url, binary=False):
    headers = {"User-Agent": "robot-video-demo-installer"}
    if binary:
        headers["Accept"] = "application/octet-stream"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        chunks, received = [], 0
        started = time.monotonic()
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
            received += len(chunk)
            if received % (2 * 1024 * 1024) == 0:
                print(f"  已下载 {received // 1024 // 1024} MiB", flush=True)
            if time.monotonic() - started > 900:
                raise TimeoutError("下载超过 15 分钟，请检查网络后重试，或按 README 手动下载")


def checked(data, expected):
    if hashlib.sha256(data).hexdigest().lower() != expected.lower():
        raise RuntimeError("SHA256 校验失败")


def main():
    RUNTIME.mkdir(exist_ok=True)
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = "amd64" if machine in ("amd64", "x86_64") else "arm64" if machine in ("arm64", "aarch64") else None
    if system not in ("windows", "linux", "darwin") or not arch:
        raise RuntimeError("请手动安装当前平台的 MediaMTX 与 FFmpeg，使用 --mediamtx 和 --ffmpeg 指定")
    suffix = "zip" if system == "windows" else "tar.gz"
    name = f"mediamtx_{VERSION}_{system}_{arch}.{suffix}"
    print("下载官方 MediaMTX", VERSION, flush=True)
    release = json.loads(fetch(f"https://api.github.com/repos/bluenviron/mediamtx/releases/tags/{VERSION}"))
    assets = {entry["name"]: entry["url"] for entry in release["assets"]}
    data = fetch(assets[name], binary=True)
    digest = fetch(assets[name + ".sha256sum"], binary=True).decode().split()[0]
    checked(data, digest)
    executable = "mediamtx.exe" if system == "windows" else "mediamtx"
    if suffix == "zip":
        with ZipFile(io.BytesIO(data)) as archive:
            payload = archive.read(executable)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            member = next(m for m in archive.getmembers() if Path(m.name).name == executable and m.isfile())
            payload = archive.extractfile(member).read()
    (RUNTIME / executable).write_bytes(payload)
    (RUNTIME / executable).chmod(0o755)
    if system == "windows" and arch == "amd64":
        # imageio-ffmpeg supplies a versioned FFmpeg binary inside its PyPI wheel.
        print("下载 FFmpeg 工具（imageio-ffmpeg 0.6.0 的 Windows 二进制）", flush=True)
        metadata = json.loads(fetch("https://pypi.org/pypi/imageio-ffmpeg/0.6.0/json"))
        wheel = next(f for f in metadata["urls"] if f["filename"].endswith("win_amd64.whl"))
        data = fetch(wheel["url"])
        checked(data, wheel["digests"]["sha256"])
        with ZipFile(io.BytesIO(data)) as archive:
            item = next(n for n in archive.namelist() if n.startswith("imageio_ffmpeg/binaries/") and n.endswith(".exe"))
            (RUNTIME / "ffmpeg.exe").write_bytes(archive.read(item))
            for entry in archive.namelist():
                if "LICENSE" in entry.upper() or "COPYING" in entry.upper():
                    (RUNTIME / ("ffmpeg-" + Path(entry).name)).write_bytes(archive.read(entry))
    elif shutil.which("ffmpeg") is None:
        print("还需安装 FFmpeg。Ubuntu: sudo apt install ffmpeg；macOS 可用包管理器安装。")
    print("工具准备完成。运行 python run_demo.py", flush=True)


if __name__ == "__main__":
    main()
