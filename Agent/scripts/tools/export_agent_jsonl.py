"""Extract JSON objects from mixed Agent logs for JSONL viewers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    count = 0
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids overwriting a live event log or previous export.
    with args.source.open(encoding="utf-8", errors="replace") as source, args.destination.open(
        "x", encoding="utf-8"
    ) as destination:
        for line in source:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                destination.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                count += 1
    print(f"Exported {count} JSON records to {args.destination}")


if __name__ == "__main__":
    main()
