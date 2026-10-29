#!/usr/bin/env python3
"""Image decoding helpers for Garden frame ingestion.

This module converts incoming frame metadata into PIL images and lightweight
dashboard previews. It intentionally does not know about prompts, sessions, or
HTTP transport so image processing stays isolated from service orchestration.
"""

import base64
import ctypes
import ctypes.util
import io
import mmap
import os

from PIL import Image


# Pillow changed the location of resampling enums; keep the compatibility shim
# here so the rest of the code can use one stable constant.
try:
    RESAMPLING_LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLING_LANCZOS = Image.LANCZOS


# Low-level shared-memory access belongs in this module rather than the server
# entrypoint because it is purely part of frame decoding.
O_RDWR = os.O_RDWR
libc = ctypes.CDLL(ctypes.util.find_library("c"))
libc.shm_open.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
libc.shm_open.restype = ctypes.c_int


def open_and_map_shm(name: str):
    """Open a POSIX shared-memory segment and map it into this process."""
    shm_name = name if name.startswith("/") else f"/{name}"
    fd = libc.shm_open(shm_name.encode("utf-8"), O_RDWR, 0)
    if fd < 0:
        raise RuntimeError(f"shm_open failed for {shm_name}")
    try:
        stat_info = os.fstat(fd)
        if stat_info.st_size <= 0:
            raise RuntimeError(f"shared memory size is invalid for {shm_name}")
        mm = mmap.mmap(fd, int(stat_info.st_size), access=mmap.ACCESS_WRITE)
        return fd, mm, int(stat_info.st_size)
    except Exception:
        os.close(fd)
        raise


def close_map(fd: int, mm: mmap.mmap) -> None:
    """Close the mmap first and then release the file descriptor."""
    try:
        mm.close()
    finally:
        os.close(fd)


def compact_rgb(raw: bytes, width: int, height: int, stride: int, channels: int) -> bytes:
    """Normalize padded RGB rows into a tightly packed byte buffer."""
    row_bytes = width * channels
    expected = row_bytes * height
    if stride == row_bytes and len(raw) >= expected:
        return raw[:expected]

    rows = []
    buf_len = len(raw)
    for row_index in range(height):
        start = row_index * stride
        end = min(start + row_bytes, buf_len)
        if start >= buf_len:
            rows.append(b"\x00" * row_bytes)
            continue
        chunk = raw[start:end]
        if len(chunk) < row_bytes:
            chunk = chunk + (b"\x00" * (row_bytes - len(chunk)))
        rows.append(chunk)
    return b"".join(rows)


def decode_image_from_meta(meta: dict) -> Image.Image:
    """Build a PIL image from base64 or shared-memory frame metadata."""
    width = int(meta.get("width", 0))
    height = int(meta.get("height", 0))
    channels = int(meta.get("channels", 3))
    stride = int(meta.get("stride", width * channels))

    if width <= 0 or height <= 0:
        raise ValueError(f"invalid frame size: width={width}, height={height}")
    if channels != 3:
        raise ValueError(f"only RGB with 3 channels is supported, got channels={channels}")

    if meta.get("base64"):
        raw = base64.b64decode(meta["base64"])
    elif meta.get("shmName"):
        fd, mm, _ = open_and_map_shm(meta["shmName"])
        try:
            shm_len = int(meta.get("shmLen", 0))
            raw = mm[:shm_len]
        finally:
            close_map(fd, mm)
    else:
        raise ValueError("meta must contain either base64 or shmName")

    rgb = compact_rgb(raw, width, height, stride, channels)
    return Image.frombytes("RGB", (width, height), rgb)


def image_to_data_url(image: Image.Image, max_width: int = 1280) -> str:
    """Create a compact JPEG data URL for the dashboard preview card."""
    preview = image.copy()
    if preview.width > max_width:
        ratio = max_width / float(preview.width)
        preview = preview.resize(
            (max_width, max(1, int(preview.height * ratio))),
            RESAMPLING_LANCZOS,
        )

    buf = io.BytesIO()
    preview.save(buf, format="JPEG", quality=85)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
