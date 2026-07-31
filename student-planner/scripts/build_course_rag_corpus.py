from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.rag_corpus import (
    load_frozen_chunks,
    write_corpus_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build or verify frozen Student Planner course RAG corpus artifacts."
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("data/rag/course_v1"),
    )
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--allow-legacy-metadata", action="store_true")
    args = parser.parse_args()

    if args.verify_only:
        manifest, chunks = load_frozen_chunks(args.corpus_dir)
        result = {
            "status": "verified",
            "corpus_dir": str(args.corpus_dir.resolve()),
            "manifest_sha256": manifest["manifest_sha256"],
            "source_count": manifest["source_count"],
            "chunk_count": len(chunks),
        }
    else:
        manifest_path, chunks_path, manifest = write_corpus_artifacts(
            args.corpus_dir,
            strict_metadata=not args.allow_legacy_metadata,
        )
        result = {
            "status": "built",
            "corpus_dir": str(args.corpus_dir.resolve()),
            "manifest": str(manifest_path.resolve()),
            "chunks": str(chunks_path.resolve()),
            "manifest_sha256": manifest["manifest_sha256"],
            "source_count": manifest["source_count"],
            "chunk_count": manifest["chunk_count"],
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
