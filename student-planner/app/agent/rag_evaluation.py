"""Thesis-grade retrieval and evidence-gate evaluation contracts."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Sequence


QUERY_TYPES = {
    "exact_entity",
    "paraphrase",
    "comparison",
    "multi_concept",
    "summary",
    "long_student_query",
    "out_of_scope",
}
ANSWERABILITY_VALUES = {"full", "partial", "none"}
CHALLENGE_EVIDENCE_TIERS = {
    "llm_assisted_unreviewed",
    "llm_assisted_single_review_silver",
    "human_double_review_gold",
}
DEFAULT_RANKING_KS = (3, 5, 10)
DEFAULT_SPLIT_SEED = 20260728
DEFAULT_BOOTSTRAP_SEED = 20260730
DEFAULT_BOOTSTRAP_ITERATIONS = 2000
PRIMARY_RANKING_METRICS = ("recall@5", "mrr", "ndcg@10")
DEFAULT_GATE_GRID = tuple(
    {
        "config_id": f"gate-v1-s{score_q:02d}-c{coverage:02d}-a{anchor:02d}",
        "score_quantile": score_q / 100,
        "min_query_coverage": coverage / 100,
        "min_anchor_coverage": anchor / 100,
        "min_segment_coverage": 0.0,
        "max_unmatched_run": 999,
    }
    for score_q in (0, 25, 50, 75)
    for coverage in (0, 50, 70)
    for anchor in (0, 45)
)


class EvaluationContractError(ValueError):
    """Raised when the golden set or evaluation output violates its contract."""


@dataclass(frozen=True)
class Qrel:
    chunk_id: str
    relevance: int


@dataclass(frozen=True)
class EvidenceRequirement:
    requirement_id: str
    any_of_chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationQuery:
    query_id: str
    query: str
    course_id: str
    query_type: str
    answerability: str
    reference_answer: str
    relevant_source_ids: tuple[str, ...]
    qrels: tuple[Qrel, ...]
    evidence_requirements: tuple[EvidenceRequirement, ...]
    expected_terms: tuple[str, ...] = ()
    split: str = ""

    @property
    def relevant_chunk_ids(self) -> tuple[str, ...]:
        return tuple(qrel.chunk_id for qrel in self.qrels if qrel.relevance > 0)

    def to_json(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "query": self.query,
            "course_id": self.course_id,
            "query_type": self.query_type,
            "answerability": self.answerability,
            "reference_answer": self.reference_answer,
            "relevant_source_ids": list(self.relevant_source_ids),
            "relevant_chunk_ids": list(self.relevant_chunk_ids),
            "qrels": [
                {"chunk_id": qrel.chunk_id, "relevance": qrel.relevance}
                for qrel in self.qrels
            ],
            "evidence_requirements": [
                {
                    "requirement_id": requirement.requirement_id,
                    "any_of_chunk_ids": list(requirement.any_of_chunk_ids),
                }
                for requirement in self.evidence_requirements
            ],
            "expected_terms": list(self.expected_terms),
            "split": self.split,
        }


def _tuple_of_strings(value: Any, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise EvaluationContractError(f"{field}_must_be_list")
    result = tuple(str(item).strip() for item in value if str(item).strip())
    if len(result) != len(set(result)):
        raise EvaluationContractError(f"{field}_contains_duplicates")
    return result


def parse_evaluation_query(row: dict[str, Any]) -> EvaluationQuery:
    query_id = str(row.get("query_id") or "").strip()
    query = str(row.get("query") or "").strip()
    course_id = str(row.get("course_id") or "").strip()
    query_type = str(row.get("query_type") or "").strip()
    answerability = str(row.get("answerability") or "").strip()
    if not query_id or not query or not course_id:
        raise EvaluationContractError("query_identity_fields_required")
    if query_type not in QUERY_TYPES:
        raise EvaluationContractError(f"invalid_query_type:{query_type}")
    if answerability not in ANSWERABILITY_VALUES:
        raise EvaluationContractError(f"invalid_answerability:{answerability}")

    raw_qrels = row.get("qrels")
    if not isinstance(raw_qrels, list):
        raise EvaluationContractError("qrels_must_be_list")
    qrels: list[Qrel] = []
    seen_chunk_ids: set[str] = set()
    for raw_qrel in raw_qrels:
        if not isinstance(raw_qrel, dict):
            raise EvaluationContractError("qrel_must_be_object")
        chunk_id = str(raw_qrel.get("chunk_id") or "").strip()
        relevance = raw_qrel.get("relevance")
        if not chunk_id or relevance not in {0, 1, 2}:
            raise EvaluationContractError("qrel_invalid")
        if chunk_id in seen_chunk_ids:
            raise EvaluationContractError(f"duplicate_qrel:{chunk_id}")
        seen_chunk_ids.add(chunk_id)
        qrels.append(Qrel(chunk_id=chunk_id, relevance=int(relevance)))

    raw_requirements = row.get("evidence_requirements") or []
    if not isinstance(raw_requirements, list):
        raise EvaluationContractError("evidence_requirements_must_be_list")
    requirements: list[EvidenceRequirement] = []
    requirement_ids: set[str] = set()
    for raw_requirement in raw_requirements:
        if not isinstance(raw_requirement, dict):
            raise EvaluationContractError("evidence_requirement_must_be_object")
        requirement_id = str(raw_requirement.get("requirement_id") or "").strip()
        chunk_ids = _tuple_of_strings(
            raw_requirement.get("any_of_chunk_ids"),
            field="any_of_chunk_ids",
        )
        if not requirement_id or not chunk_ids:
            raise EvaluationContractError("evidence_requirement_invalid")
        if requirement_id in requirement_ids:
            raise EvaluationContractError(
                f"duplicate_evidence_requirement:{requirement_id}"
            )
        if not set(chunk_ids).issubset(seen_chunk_ids):
            raise EvaluationContractError(
                f"requirement_chunk_missing_from_qrels:{requirement_id}"
            )
        requirement_ids.add(requirement_id)
        requirements.append(
            EvidenceRequirement(
                requirement_id=requirement_id,
                any_of_chunk_ids=chunk_ids,
            )
        )
    if requirements and answerability != "full":
        raise EvaluationContractError(
            "evidence_requirements_only_allowed_for_full_queries"
        )

    query_item = EvaluationQuery(
        query_id=query_id,
        query=query,
        course_id=course_id,
        query_type=query_type,
        answerability=answerability,
        reference_answer=str(row.get("reference_answer") or "").strip(),
        relevant_source_ids=_tuple_of_strings(
            row.get("relevant_source_ids"),
            field="relevant_source_ids",
        ),
        qrels=tuple(qrels),
        evidence_requirements=tuple(requirements),
        expected_terms=_tuple_of_strings(
            row.get("expected_terms") or [],
            field="expected_terms",
        ),
        split=str(row.get("split") or "").strip(),
    )
    provided_relevant = row.get("relevant_chunk_ids")
    if provided_relevant is not None:
        relevant_chunk_ids = _tuple_of_strings(
            provided_relevant,
            field="relevant_chunk_ids",
        )
        if set(relevant_chunk_ids) != set(query_item.relevant_chunk_ids):
            raise EvaluationContractError(
                f"relevant_chunk_ids_not_derived_from_qrels:{query_id}"
            )
    if answerability == "full" and not query_item.relevant_chunk_ids:
        raise EvaluationContractError(f"full_query_requires_relevant_qrels:{query_id}")
    if answerability == "none" and query_item.relevant_chunk_ids:
        raise EvaluationContractError(f"none_query_cannot_have_relevant_qrels:{query_id}")
    return query_item


def load_evaluation_queries(path: str | Path) -> list[EvaluationQuery]:
    dataset_path = Path(path)
    queries: list[EvaluationQuery] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(
        dataset_path.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationContractError(
                f"dataset_json_invalid:{line_number}"
            ) from exc
        query = parse_evaluation_query(row)
        if query.query_id in seen_ids:
            raise EvaluationContractError(f"duplicate_query_id:{query.query_id}")
        seen_ids.add(query.query_id)
        queries.append(query)
    if not queries:
        raise EvaluationContractError("dataset_empty")
    return queries


def stratified_split(
    queries: Sequence[EvaluationQuery],
    *,
    development_ratio: float = 0.3,
    seed: int = DEFAULT_SPLIT_SEED,
) -> dict[str, str]:
    if not 0.0 < development_ratio < 1.0:
        raise ValueError("development_ratio_must_be_between_zero_and_one")
    strata: dict[tuple[str, str, str], list[EvaluationQuery]] = {}
    for query in queries:
        strata.setdefault(
            (query.course_id, query.query_type, query.answerability),
            [],
        ).append(query)

    rng = random.Random(seed)
    assignments: dict[str, str] = {}
    for key in sorted(strata):
        items = sorted(strata[key], key=lambda item: item.query_id)
        rng.shuffle(items)
        if len(items) == 1:
            development_count = 0
        else:
            development_count = max(
                1,
                min(len(items) - 1, round(len(items) * development_ratio)),
            )
        for index, query in enumerate(items):
            assignments[query.query_id] = (
                "development" if index < development_count else "test"
            )

    target_development = round(len(queries) * development_ratio)
    current_development = sum(
        1 for split in assignments.values() if split == "development"
    )
    ordered = sorted(
        queries,
        key=lambda query: hashlib.sha256(
            f"{seed}:{query.query_id}".encode("utf-8")
        ).hexdigest(),
    )
    if current_development < target_development:
        for query in ordered:
            if assignments[query.query_id] == "test":
                assignments[query.query_id] = "development"
                current_development += 1
                if current_development >= target_development:
                    break
    elif current_development > target_development:
        for query in ordered:
            if assignments[query.query_id] == "development":
                assignments[query.query_id] = "test"
                current_development -= 1
                if current_development <= target_development:
                    break
    return assignments


def _hit_chunk_id(hit: dict[str, Any]) -> str:
    metadata = dict(hit.get("metadata") or {})
    return str(hit.get("chunk_id") or metadata.get("chunk_id") or "")


def _hit_source_id(hit: dict[str, Any]) -> str:
    metadata = dict(hit.get("metadata") or {})
    return str(
        hit.get("source_id")
        or hit.get("source")
        or metadata.get("source_id")
        or metadata.get("source")
        or ""
    ).replace("\\", "/")


def _dcg(relevances: Sequence[int]) -> float:
    return sum(
        ((2**relevance) - 1) / math.log2(rank + 1)
        for rank, relevance in enumerate(relevances, 1)
    )


def evaluate_ranked_query(
    query: EvaluationQuery,
    hits: Sequence[dict[str, Any]],
    *,
    ks: Sequence[int] = DEFAULT_RANKING_KS,
) -> dict[str, Any]:
    qrel_map = {qrel.chunk_id: qrel.relevance for qrel in query.qrels}
    relevant_ids = {
        chunk_id for chunk_id, relevance in qrel_map.items() if relevance >= 1
    }
    ranked_chunk_ids = [_hit_chunk_id(hit) for hit in hits]
    ranked_sources = [_hit_source_id(hit) for hit in hits]
    row: dict[str, Any] = {
        "query_id": query.query_id,
        "course_id": query.course_id,
        "query_type": query.query_type,
        "answerability": query.answerability,
        "ranked_chunk_ids": ranked_chunk_ids,
        "top1_source_hit": bool(ranked_sources)
        and ranked_sources[0] in set(query.relevant_source_ids),
    }
    first_relevant_rank = next(
        (
            rank
            for rank, chunk_id in enumerate(ranked_chunk_ids, 1)
            if chunk_id in relevant_ids
        ),
        None,
    )
    row["mrr"] = 1.0 / first_relevant_rank if first_relevant_rank else 0.0
    for k in ks:
        top_ids = ranked_chunk_ids[:k]
        relevant_hits = sum(1 for chunk_id in top_ids if chunk_id in relevant_ids)
        row[f"recall@{k}"] = (
            relevant_hits / len(relevant_ids) if relevant_ids else 0.0
        )
        row[f"precision@{k}"] = relevant_hits / k
        judged_count = sum(1 for chunk_id in top_ids if chunk_id in qrel_map)
        row[f"judged@{k}"] = judged_count / k
        actual_relevances = [qrel_map.get(chunk_id, 0) for chunk_id in top_ids]
        ideal_relevances = sorted(qrel_map.values(), reverse=True)[:k]
        ideal_dcg = _dcg(ideal_relevances)
        row[f"ndcg@{k}"] = (
            _dcg(actual_relevances) / ideal_dcg if ideal_dcg else 0.0
        )

    if query.answerability == "full" and query.evidence_requirements:
        top_10_ids = set(ranked_chunk_ids[:10])
        requirement_hits = [
            bool(top_10_ids.intersection(requirement.any_of_chunk_ids))
            for requirement in query.evidence_requirements
        ]
        row["requirement_recall@10"] = sum(requirement_hits) / len(
            requirement_hits
        )
        row["complete_evidence_recall@10"] = float(all(requirement_hits))
    else:
        row["requirement_recall@10"] = None
        row["complete_evidence_recall@10"] = None
    return row


def summarize_ranking_rows(
    rows: Sequence[dict[str, Any]],
    *,
    ks: Sequence[int] = DEFAULT_RANKING_KS,
) -> dict[str, Any]:
    metric_names = ["mrr", "top1_source_hit"]
    for k in ks:
        metric_names.extend(
            [f"recall@{k}", f"precision@{k}", f"judged@{k}", f"ndcg@{k}"]
        )
    metric_names.extend(["requirement_recall@10", "complete_evidence_recall@10"])

    def summarize_group(group_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {"query_count": len(group_rows)}
        for metric_name in metric_names:
            values = [
                float(row[metric_name])
                for row in group_rows
                if row.get(metric_name) is not None
            ]
            result[metric_name] = round(mean(values), 6) if values else None
        latencies = [
            float(row["latency_ms"])
            for row in group_rows
            if row.get("latency_ms") is not None
        ]
        if latencies:
            ordered = sorted(latencies)
            p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
            result["latency_mean_ms"] = round(mean(latencies), 3)
            result["latency_p95_ms"] = round(ordered[p95_index], 3)
        result["estimated_cost"] = round(
            sum(float(row.get("estimated_cost") or 0.0) for row in group_rows),
            8,
        )
        return result

    dimensions = ("course_id", "query_type", "answerability")
    return {
        "overall": summarize_group(rows),
        "by": {
            dimension: {
                value: summarize_group(
                    [row for row in rows if str(row.get(dimension)) == value]
                )
                for value in sorted({str(row.get(dimension)) for row in rows})
            }
            for dimension in dimensions
        },
    }


def summarize_ranking_rows_by_split(
    rows: Sequence[dict[str, Any]],
    *,
    ks: Sequence[int] = DEFAULT_RANKING_KS,
) -> dict[str, Any]:
    """Keep development and test summaries separate.

    Benchmark v2 never mixes development rows into its primary test table.
    """

    summaries: dict[str, Any] = {}
    for split in ("development", "test", "holdout"):
        split_rows = [row for row in rows if row.get("split") == split]
        if split_rows:
            summaries[split] = summarize_ranking_rows(split_rows, ks=ks)
    return summaries


def _percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise EvaluationContractError("percentile_requires_values")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability_must_be_between_zero_and_one")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return ordered[lower_index] + (
        ordered[upper_index] - ordered[lower_index]
    ) * fraction


def bootstrap_metric_intervals(
    rows: Sequence[dict[str, Any]],
    *,
    metric_names: Sequence[str] = PRIMARY_RANKING_METRICS,
    iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Return deterministic query-level bootstrap confidence intervals."""

    if iterations < 100:
        raise ValueError("bootstrap_iterations_must_be_at_least_100")
    intervals: dict[str, Any] = {}
    for metric_name in metric_names:
        values = [
            float(row[metric_name])
            for row in rows
            if row.get(metric_name) is not None
        ]
        if not values:
            intervals[metric_name] = None
            continue
        rng = random.Random(f"{seed}:{metric_name}")
        estimates = [
            mean(rng.choice(values) for _ in range(len(values)))
            for _ in range(iterations)
        ]
        intervals[metric_name] = {
            "query_count": len(values),
            "mean": round(mean(values), 6),
            "ci95_low": round(_percentile(estimates, 0.025), 6),
            "ci95_high": round(_percentile(estimates, 0.975), 6),
            "iterations": iterations,
            "seed": seed,
        }
    return intervals


def paired_bootstrap_comparisons(
    rows_by_mode: dict[str, Sequence[dict[str, Any]]],
    *,
    baseline_mode: str = "embedding_only",
    metric_names: Sequence[str] = PRIMARY_RANKING_METRICS,
    iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> list[dict[str, Any]]:
    """Compare every mode against a baseline using aligned query-level rows."""

    if iterations < 100:
        raise ValueError("bootstrap_iterations_must_be_at_least_100")
    if baseline_mode not in rows_by_mode:
        raise EvaluationContractError(f"baseline_mode_missing:{baseline_mode}")

    baseline_by_query = {
        str(row["query_id"]): row for row in rows_by_mode[baseline_mode]
    }
    comparisons: list[dict[str, Any]] = []
    for mode, rows in rows_by_mode.items():
        if mode == baseline_mode:
            continue
        candidate_by_query = {str(row["query_id"]): row for row in rows}
        if set(candidate_by_query) != set(baseline_by_query):
            raise EvaluationContractError(
                f"paired_query_ids_mismatch:{baseline_mode}:{mode}"
            )
        query_ids = sorted(baseline_by_query)
        for metric_name in metric_names:
            paired_differences = [
                float(candidate_by_query[query_id][metric_name])
                - float(baseline_by_query[query_id][metric_name])
                for query_id in query_ids
                if candidate_by_query[query_id].get(metric_name) is not None
                and baseline_by_query[query_id].get(metric_name) is not None
            ]
            if not paired_differences:
                continue
            rng = random.Random(f"{seed}:{baseline_mode}:{mode}:{metric_name}")
            estimates = [
                mean(
                    rng.choice(paired_differences)
                    for _ in range(len(paired_differences))
                )
                for _ in range(iterations)
            ]
            ci_low = _percentile(estimates, 0.025)
            ci_high = _percentile(estimates, 0.975)
            direction = "inconclusive"
            if ci_low > 0:
                direction = "improvement"
            elif ci_high < 0:
                direction = "degradation"
            comparisons.append(
                {
                    "baseline_mode": baseline_mode,
                    "mode": mode,
                    "metric": metric_name,
                    "query_count": len(paired_differences),
                    "mean_difference": round(mean(paired_differences), 6),
                    "ci95_low": round(ci_low, 6),
                    "ci95_high": round(ci_high, 6),
                    "direction": direction,
                    "iterations": iterations,
                    "seed": seed,
                }
            )
    return comparisons


def _quantile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * quantile)))
    return float(ordered[index])


def _gate_accepts(hits: Sequence[dict[str, Any]], config: dict[str, Any]) -> bool:
    for hit in hits:
        if float(hit.get("score") or 0.0) < float(config["min_score"]):
            continue
        if float(hit.get("query_coverage") or 0.0) < float(
            config["min_query_coverage"]
        ):
            continue
        if float(hit.get("anchor_coverage") or 0.0) < float(
            config["min_anchor_coverage"]
        ):
            continue
        if float(hit.get("segment_coverage") or 0.0) < float(
            config["min_segment_coverage"]
        ):
            continue
        if int(hit.get("unmatched_run") or 0) > int(config["max_unmatched_run"]):
            continue
        return True
    return False


def _binary_macro_f1(
    expected_accept: Sequence[bool],
    predicted_accept: Sequence[bool],
) -> float:
    f1_values: list[float] = []
    for positive_label in (True, False):
        true_positive = sum(
            1
            for expected, predicted in zip(
                expected_accept,
                predicted_accept,
                strict=True,
            )
            if expected == positive_label and predicted == positive_label
        )
        false_positive = sum(
            1
            for expected, predicted in zip(
                expected_accept,
                predicted_accept,
                strict=True,
            )
            if expected != positive_label and predicted == positive_label
        )
        false_negative = sum(
            1
            for expected, predicted in zip(
                expected_accept,
                predicted_accept,
                strict=True,
            )
            if expected == positive_label and predicted != positive_label
        )
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0.0
        )
        f1_values.append(
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
    return mean(f1_values)


def evaluate_gate_config(
    rows: Sequence[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    expected_accept = [row["answerability"] == "full" for row in rows]
    predicted_accept = [_gate_accepts(row.get("hits") or [], config) for row in rows]
    insufficient_indexes = [
        index
        for index, row in enumerate(rows)
        if row["answerability"] in {"partial", "none"}
    ]
    full_indexes = [
        index for index, row in enumerate(rows) if row["answerability"] == "full"
    ]
    false_accept_count = sum(
        1 for index in insufficient_indexes if predicted_accept[index]
    )
    rejected_insufficient = sum(
        1 for index in insufficient_indexes if not predicted_accept[index]
    )
    accepted_full = sum(1 for index in full_indexes if predicted_accept[index])
    return {
        **config,
        "false_accept_rate": (
            false_accept_count / len(insufficient_indexes)
            if insufficient_indexes
            else 0.0
        ),
        "macro_f1": _binary_macro_f1(expected_accept, predicted_accept),
        "insufficient_recall": (
            rejected_insufficient / len(insufficient_indexes)
            if insufficient_indexes
            else 0.0
        ),
        "full_answer_recall": (
            accepted_full / len(full_indexes) if full_indexes else 0.0
        ),
        "predictions": {
            row["query_id"]: "accept" if prediction else "reject"
            for row, prediction in zip(rows, predicted_accept, strict=True)
        },
    }


def calibrate_gate(
    development_rows: Sequence[dict[str, Any]],
    *,
    parameter_grid: Sequence[dict[str, Any]] = DEFAULT_GATE_GRID,
) -> dict[str, Any]:
    if not development_rows:
        raise EvaluationContractError("gate_calibration_requires_development_rows")
    top_scores = [
        max(
            (float(hit.get("score") or 0.0) for hit in row.get("hits") or []),
            default=0.0,
        )
        for row in development_rows
    ]
    evaluated: list[dict[str, Any]] = []
    for raw_config in parameter_grid:
        config = dict(raw_config)
        config["min_score"] = round(
            _quantile(top_scores, float(config.pop("score_quantile"))),
            8,
        )
        evaluated.append(evaluate_gate_config(development_rows, config))

    constrained = [
        config for config in evaluated if config["false_accept_rate"] <= 0.05
    ]
    constraint_met = bool(constrained)
    candidates = constrained or evaluated
    if constraint_met:
        candidates.sort(
            key=lambda config: (
                -float(config["macro_f1"]),
                -float(config["insufficient_recall"]),
                -float(config["full_answer_recall"]),
                str(config["config_id"]),
            )
        )
    else:
        candidates.sort(
            key=lambda config: (
                float(config["false_accept_rate"]),
                -float(config["macro_f1"]),
                -float(config["insufficient_recall"]),
                -float(config["full_answer_recall"]),
                str(config["config_id"]),
            )
        )
    selected = candidates[0]
    return {
        "constraint": "partial_none_false_accept_rate<=0.05",
        "constraint_met": constraint_met,
        "selected_config_id": selected["config_id"],
        "selected_config": {
            key: value for key, value in selected.items() if key != "predictions"
        },
        "configs": [
            {key: value for key, value in config.items() if key != "predictions"}
            for config in evaluated
        ],
    }


def apply_frozen_gate(
    rows: Sequence[dict[str, Any]],
    selected_config: dict[str, Any],
) -> dict[str, Any]:
    return evaluate_gate_config(rows, selected_config)


def dataset_sha256(queries: Sequence[EvaluationQuery]) -> str:
    rendered = "".join(
        json.dumps(query.to_json(), ensure_ascii=False, sort_keys=True) + "\n"
        for query in queries
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def build_dataset_manifest(
    queries: Sequence[EvaluationQuery],
    *,
    dataset_version: str,
    corpus_manifest_sha256: str,
    split_seed: int = DEFAULT_SPLIT_SEED,
) -> dict[str, Any]:
    return {
        "schema_version": "course-rag-golden-set-v1",
        "dataset_version": dataset_version,
        "corpus_manifest_sha256": corpus_manifest_sha256,
        "query_count": len(queries),
        "qrel_count": sum(len(query.qrels) for query in queries),
        "development_count": sum(
            1 for query in queries if query.split == "development"
        ),
        "test_count": sum(1 for query in queries if query.split == "test"),
        "split_seed": split_seed,
        "query_types": sorted({query.query_type for query in queries}),
        "answerability": sorted({query.answerability for query in queries}),
        "dataset_sha256": dataset_sha256(queries),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_challenge_manifest(
    queries: Sequence[EvaluationQuery],
    *,
    dataset_version: str,
    corpus_manifest_sha256: str,
    evidence_tier: str,
    frozen_config_sha256: str,
) -> dict[str, Any]:
    if evidence_tier not in CHALLENGE_EVIDENCE_TIERS:
        raise EvaluationContractError(
            f"invalid_challenge_evidence_tier:{evidence_tier}"
        )
    if not frozen_config_sha256:
        raise EvaluationContractError("challenge_requires_frozen_config_sha256")
    return {
        "schema_version": "course-rag-challenge-v1",
        "dataset_version": dataset_version,
        "corpus_manifest_sha256": corpus_manifest_sha256,
        "query_count": len(queries),
        "qrel_count": sum(len(query.qrels) for query in queries),
        "query_types": sorted({query.query_type for query in queries}),
        "answerability": sorted({query.answerability for query in queries}),
        "dataset_sha256": dataset_sha256(queries),
        "evidence_tier": evidence_tier,
        "frozen_config_sha256": frozen_config_sha256,
        "used_for_tuning": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_challenge_contract(
    challenge_queries: Sequence[EvaluationQuery],
    *,
    main_queries: Sequence[EvaluationQuery],
    challenge_manifest: dict[str, Any],
    corpus_manifest_sha256: str,
    known_chunk_ids: set[str],
    known_source_ids: set[str],
) -> dict[str, Any]:
    errors: list[str] = []
    if challenge_manifest.get("schema_version") != "course-rag-challenge-v1":
        errors.append("challenge_schema_version_invalid")
    if challenge_manifest.get("corpus_manifest_sha256") != corpus_manifest_sha256:
        errors.append("challenge_corpus_manifest_mismatch")
    if challenge_manifest.get("dataset_sha256") != dataset_sha256(
        challenge_queries
    ):
        errors.append("challenge_dataset_hash_mismatch")
    if challenge_manifest.get("query_count") != len(challenge_queries):
        errors.append("challenge_query_count_mismatch")
    if challenge_manifest.get("used_for_tuning") is not False:
        errors.append("challenge_must_not_be_used_for_tuning")
    if challenge_manifest.get("evidence_tier") not in CHALLENGE_EVIDENCE_TIERS:
        errors.append("challenge_evidence_tier_invalid")
    if not challenge_manifest.get("frozen_config_sha256"):
        errors.append("challenge_missing_frozen_config_sha256")
    if not 24 <= len(challenge_queries) <= 32:
        errors.append("challenge_query_count_out_of_range")

    main_query_ids = {query.query_id for query in main_queries}
    main_query_texts = {query.query.strip().casefold() for query in main_queries}
    challenge_query_ids: set[str] = set()
    challenge_query_texts: set[str] = set()
    course_counts: dict[str, int] = {}
    answerability_counts = {value: 0 for value in ANSWERABILITY_VALUES}
    query_types: set[str] = set()
    for query in challenge_queries:
        normalized_text = query.query.strip().casefold()
        if query.split != "holdout":
            errors.append(f"challenge_split_must_be_holdout:{query.query_id}")
        if query.query_id in main_query_ids:
            errors.append(f"challenge_query_id_overlaps_main:{query.query_id}")
        if normalized_text in main_query_texts:
            errors.append(f"challenge_query_text_overlaps_main:{query.query_id}")
        if query.query_id in challenge_query_ids:
            errors.append(f"duplicate_challenge_query_id:{query.query_id}")
        if normalized_text in challenge_query_texts:
            errors.append(f"duplicate_challenge_query_text:{query.query_id}")
        challenge_query_ids.add(query.query_id)
        challenge_query_texts.add(normalized_text)
        course_counts[query.course_id] = course_counts.get(query.course_id, 0) + 1
        answerability_counts[query.answerability] += 1
        query_types.add(query.query_type)
        if not {qrel.chunk_id for qrel in query.qrels}.issubset(known_chunk_ids):
            errors.append(f"challenge_unknown_qrel_chunk:{query.query_id}")
        if not set(query.relevant_source_ids).issubset(known_source_ids):
            errors.append(f"challenge_unknown_relevant_source:{query.query_id}")

    required_query_types = {
        "paraphrase",
        "multi_concept",
        "long_student_query",
        "out_of_scope",
    }
    if not required_query_types.issubset(query_types):
        errors.append("challenge_hard_query_type_coverage_incomplete")
    if len(course_counts) != 4 or any(count < 4 for count in course_counts.values()):
        errors.append("challenge_course_coverage_incomplete")
    if answerability_counts["partial"] < 4:
        errors.append("challenge_partial_count_below_four")
    if answerability_counts["none"] < 4:
        errors.append("challenge_none_count_below_four")
    if errors:
        raise EvaluationContractError(";".join(errors))
    return {
        "status": "valid",
        "schema_version": challenge_manifest["schema_version"],
        "dataset_version": challenge_manifest.get("dataset_version"),
        "query_count": len(challenge_queries),
        "course_counts": dict(sorted(course_counts.items())),
        "query_types": sorted(query_types),
        "answerability": answerability_counts,
        "evidence_tier": challenge_manifest["evidence_tier"],
        "dataset_sha256": challenge_manifest["dataset_sha256"],
        "frozen_config_sha256": challenge_manifest["frozen_config_sha256"],
    }


def write_rows_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def write_summary_csv(
    path: str | Path,
    summaries: dict[str, Any],
    *,
    split: str | None = None,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for mode, summary in summaries.items():
        if split is not None:
            if split not in summary:
                raise EvaluationContractError(
                    f"summary_split_missing:{mode}:{split}"
                )
            summary = summary[split]
        rows.append({"mode": mode, "group": "overall", **summary["overall"]})
        for dimension, groups in summary.get("by", {}).items():
            for value, metrics in groups.items():
                rows.append(
                    {
                        "mode": mode,
                        "group": f"{dimension}:{value}",
                        **metrics,
                    }
                )
    fieldnames = sorted({key for row in rows for key in row})
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
