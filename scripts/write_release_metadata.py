from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import argparse
import json
import os


def hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    args = parser.parse_args()
    payload = {
        "release_id": args.release_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": os.environ.get("GITHUB_SHA", "local"),
        "source_manifest": args.manifest.name,
        "source_manifest_sha256": hash_file(args.manifest),
        "catalog": args.catalog.name,
        "catalog_sha256": hash_file(args.catalog),
        "pipeline_version": "1.0.0",
        "time_semantics": "[open_time_us, close_time_exclusive_us); available at close_time_exclusive_us",
        "gap_policy": "report, never price-fill",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
