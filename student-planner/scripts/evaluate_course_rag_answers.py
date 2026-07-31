from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.rag_answer_evaluation import (
    evaluate_answer_item,
    load_jsonl,
    parse_answer_judgment,
    parse_answer_run,
    summarize_answer_rows,
    write_jsonl,
)
from app.agent.rag_evaluation import (
    EvaluationContractError,
    load_evaluation_queries,
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_answer_files(
    *,
    dataset_path: Path,
    answer_runs_path: Path,
    judgments_path: Path,
    output_dir: Path,
) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise EvaluationContractError(
            f"output_directory_must_be_empty:{output_dir.resolve()}"
        )
    queries = {
        query.query_id: query for query in load_evaluation_queries(dataset_path)
    }
    runs = [parse_answer_run(row) for row in load_jsonl(answer_runs_path)]
    judgments = [
        parse_answer_judgment(row) for row in load_jsonl(judgments_path)
    ]
    run_keys = [(run.query_id, run.mode) for run in runs]
    judgment_by_key = {
        (judgment.query_id, judgment.mode): judgment
        for judgment in judgments
    }
    if len(run_keys) != len(set(run_keys)):
        raise EvaluationContractError("duplicate_answer_run_key")
    if set(run_keys) != set(judgment_by_key):
        raise EvaluationContractError("answer_run_judgment_keys_mismatch")
    unknown_queries = {
        query_id for query_id, _ in run_keys if query_id not in queries
    }
    if unknown_queries:
        raise EvaluationContractError(
            "answer_runs_reference_unknown_queries:"
            + ",".join(sorted(unknown_queries))
        )
    rows = [
        evaluate_answer_item(
            queries[run.query_id],
            run,
            judgment_by_key[(run.query_id, run.mode)],
        )
        for run in runs
    ]
    summary = summarize_answer_rows(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "answer_results.jsonl", rows)
    (output_dir / "answer_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    chart_rows = [
        {"mode": mode, **metrics}
        for mode, metrics in summary["by_mode"].items()
    ]
    fieldnames = sorted({key for row in chart_rows for key in row}) or ["mode"]
    for filename in ("answer_summary.csv", "chart_answer_quality.csv"):
        with (output_dir / filename).open(
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(chart_rows)
    output_files = sorted(path for path in output_dir.iterdir() if path.is_file())
    manifest = {
        "schema_version": "course-rag-answer-run-v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(dataset_path.resolve()),
        "dataset_sha256": _sha256_file(dataset_path),
        "answer_runs_path": str(answer_runs_path.resolve()),
        "answer_runs_sha256": _sha256_file(answer_runs_path),
        "judgments_path": str(judgments_path.resolve()),
        "judgments_sha256": _sha256_file(judgments_path),
        "query_count": len({run.query_id for run in runs}),
        "run_count": len(runs),
        "modes": sorted({run.mode for run in runs}),
        "outputs": {
            path.name: {
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in output_files
        },
    }
    (output_dir / "answer_run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate saved Benchmark v2 RAG answers and independent support/"
            "nugget judgments without making online calls."
        )
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--answer-runs", type=Path, required=True)
    parser.add_argument("--judgments", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = evaluate_answer_files(
        dataset_path=args.dataset,
        answer_runs_path=args.answer_runs,
        judgments_path=args.judgments,
        output_dir=args.output_dir,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
