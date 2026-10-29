"""Download an official YOLOv5 checkpoint from Hugging Face Hub.

Examples:
    python download_model.py --model yolov5s
    python download_model.py --model yolov5x --output-dir ./weights
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


DEFAULT_REPOSITORY = "Ultralytics/YOLOv5"
MODEL_VARIANTS = {
    "yolov5n": "yolov5n.pt",  # Nano, about 3.2M parameters.
    "yolov5s": "yolov5s.pt",  # Small, about 11.2M parameters.
    "yolov5m": "yolov5m.pt",  # Medium, about 25.9M parameters.
    "yolov5l": "yolov5l.pt",  # Large, about 43.7M parameters.
    "yolov5x": "yolov5x.pt",  # XLarge, about 68.2M parameters.
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a YOLOv8 checkpoint from Hugging Face Hub."
    )
    parser.add_argument(
        "--model",
        default="yolov5s",
        choices=MODEL_VARIANTS,
        help="YOLOv8 size to download (default: yolov8s).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory where the checkpoint is saved (default: this script's directory).",
    )
    parser.add_argument(
        "--repo-id",
        default=DEFAULT_REPOSITORY,
        help="Hugging Face repository containing the checkpoint.",
    )
    parser.add_argument(
        "--revision",
        default=None,
        help="Optional Hugging Face repository revision, tag, or commit SHA.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Download again even when the file is already cached.",
    )
    return parser.parse_args()


def download_model(
    model: str,
    output_dir: Path,
    repo_id: str = DEFAULT_REPOSITORY,
    revision: str | None = None,
    force_download: bool = False,
) -> Path:
    """Download *model* and return its local checkpoint path."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as error:
        raise RuntimeError(
            "Missing dependency: install it with 'pip install huggingface_hub'."
        ) from error

    filename = MODEL_VARIANTS[model]
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        revision=revision,
        local_dir=output_dir,
        force_download=force_download,
    )
    return Path(checkpoint_path)


def main() -> None:
    args = parse_args()
    try:
        checkpoint_path = download_model(
            model=args.model,
            output_dir=args.output_dir,
            repo_id=args.repo_id,
            revision=args.revision,
            force_download=args.force_download,
        )
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    print("Downloaded %s -> %s" % (args.model, checkpoint_path))


if __name__ == "__main__":
    main()
