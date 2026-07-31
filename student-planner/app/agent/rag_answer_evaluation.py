"""Benchmark v2 contracts for evaluating generated RAG answers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Sequence

from app.agent.rag_evaluation import EvaluationContractError, EvaluationQuery


SUPPORT_VALUES = {0, 1, 2}
COVERAGE_VALUES = {0, 1, 2}


@dataclass(frozen=True)
class AnswerSentence:
    sentence_id: str
    text: str
    citation_chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class AnswerRun:
    query_id: str
    mode: str
    answer: str
    refused: bool
    evidence_chunk_ids: tuple[str, ...]
    sentences: tuple[AnswerSentence, ...]
    model: str
    prompt_version: str
    temperature: float


@dataclass(frozen=True)
class SentenceJudgment:
    sentence_id: str
    requires_citation: bool
    support: int


@dataclass(frozen=True)
class NuggetJudgment:
    nugget_id: str
    importance: str
    coverage: int


@dataclass(frozen=True)
class AnswerJudgment:
    query_id: str
    mode: str
    sentence_judgments: tuple[SentenceJudgment, ...]
    nugget_judgments: tuple[NuggetJudgment, ...]
    completeness: int
    judge_model: str
    rubric_version: str
    human_audit_status: str


def _unique_strings(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise EvaluationContractError(f"{field}_must_be_list")
    result = tuple(str(item).strip() for item in value)
    if any(not item for item in result):
        raise EvaluationContractError(f"{field}_contains_empty_value")
    if len(result) != len(set(result)):
        raise EvaluationContractError(f"{field}_contains_duplicates")
    return result


def parse_answer_run(row: dict[str, Any]) -> AnswerRun:
    query_id = str(row.get("query_id") or "").strip()
    mode = str(row.get("mode") or "").strip()
    model = str(row.get("model") or "").strip()
    prompt_version = str(row.get("prompt_version") or "").strip()
    if not all((query_id, mode, model, prompt_version)):
        raise EvaluationContractError("answer_run_missing_identity_or_model")
    refused = row.get("refused")
    if not isinstance(refused, bool):
        raise EvaluationContractError("answer_run_refused_must_be_boolean")
    evidence_chunk_ids = _unique_strings(
        row.get("evidence_chunk_ids"),
        field="answer_run_evidence_chunk_ids",
    )
    raw_sentences = row.get("sentences")
    if not isinstance(raw_sentences, list):
        raise EvaluationContractError("answer_run_sentences_must_be_list")
    sentences: list[AnswerSentence] = []
    sentence_ids: set[str] = set()
    for raw_sentence in raw_sentences:
        if not isinstance(raw_sentence, dict):
            raise EvaluationContractError("answer_sentence_must_be_object")
        sentence_id = str(raw_sentence.get("sentence_id") or "").strip()
        text = str(raw_sentence.get("text") or "").strip()
        if not sentence_id or not text:
            raise EvaluationContractError("answer_sentence_missing_id_or_text")
        if sentence_id in sentence_ids:
            raise EvaluationContractError(
                f"duplicate_answer_sentence_id:{sentence_id}"
            )
        sentence_ids.add(sentence_id)
        sentences.append(
            AnswerSentence(
                sentence_id=sentence_id,
                text=text,
                citation_chunk_ids=_unique_strings(
                    raw_sentence.get("citation_chunk_ids"),
                    field=f"answer_sentence_citations:{sentence_id}",
                ),
            )
        )
    answer = str(row.get("answer") or "").strip()
    if refused and not answer:
        raise EvaluationContractError("refusal_requires_user_visible_answer")
    if not refused and (not answer or not sentences):
        raise EvaluationContractError("non_refusal_requires_answer_sentences")
    try:
        temperature = float(row.get("temperature"))
    except (TypeError, ValueError) as error:
        raise EvaluationContractError(
            "answer_run_temperature_must_be_number"
        ) from error
    return AnswerRun(
        query_id=query_id,
        mode=mode,
        answer=answer,
        refused=refused,
        evidence_chunk_ids=evidence_chunk_ids,
        sentences=tuple(sentences),
        model=model,
        prompt_version=prompt_version,
        temperature=temperature,
    )


def parse_answer_judgment(row: dict[str, Any]) -> AnswerJudgment:
    query_id = str(row.get("query_id") or "").strip()
    mode = str(row.get("mode") or "").strip()
    judge_model = str(row.get("judge_model") or "").strip()
    rubric_version = str(row.get("rubric_version") or "").strip()
    human_audit_status = str(row.get("human_audit_status") or "").strip()
    if not all(
        (query_id, mode, judge_model, rubric_version, human_audit_status)
    ):
        raise EvaluationContractError("answer_judgment_missing_metadata")
    raw_sentence_judgments = row.get("sentence_judgments")
    if not isinstance(raw_sentence_judgments, list):
        raise EvaluationContractError(
            "sentence_judgments_must_be_list"
        )
    sentence_judgments: list[SentenceJudgment] = []
    sentence_ids: set[str] = set()
    for raw_judgment in raw_sentence_judgments:
        if not isinstance(raw_judgment, dict):
            raise EvaluationContractError("sentence_judgment_must_be_object")
        sentence_id = str(raw_judgment.get("sentence_id") or "").strip()
        requires_citation = raw_judgment.get("requires_citation")
        support = raw_judgment.get("support")
        if not sentence_id or not isinstance(requires_citation, bool):
            raise EvaluationContractError(
                "sentence_judgment_missing_id_or_requires_citation"
            )
        if support not in SUPPORT_VALUES:
            raise EvaluationContractError(
                f"invalid_sentence_support:{sentence_id}"
            )
        if sentence_id in sentence_ids:
            raise EvaluationContractError(
                f"duplicate_sentence_judgment:{sentence_id}"
            )
        sentence_ids.add(sentence_id)
        sentence_judgments.append(
            SentenceJudgment(
                sentence_id=sentence_id,
                requires_citation=requires_citation,
                support=int(support),
            )
        )
    raw_nuggets = row.get("nugget_judgments")
    if not isinstance(raw_nuggets, list):
        raise EvaluationContractError("nugget_judgments_must_be_list")
    nugget_judgments: list[NuggetJudgment] = []
    nugget_ids: set[str] = set()
    for raw_nugget in raw_nuggets:
        if not isinstance(raw_nugget, dict):
            raise EvaluationContractError("nugget_judgment_must_be_object")
        nugget_id = str(raw_nugget.get("nugget_id") or "").strip()
        importance = str(raw_nugget.get("importance") or "").strip()
        coverage = raw_nugget.get("coverage")
        if not nugget_id or importance not in {"vital", "okay"}:
            raise EvaluationContractError(
                "nugget_judgment_missing_id_or_importance"
            )
        if coverage not in COVERAGE_VALUES:
            raise EvaluationContractError(f"invalid_nugget_coverage:{nugget_id}")
        if nugget_id in nugget_ids:
            raise EvaluationContractError(
                f"duplicate_nugget_judgment:{nugget_id}"
            )
        nugget_ids.add(nugget_id)
        nugget_judgments.append(
            NuggetJudgment(
                nugget_id=nugget_id,
                importance=importance,
                coverage=int(coverage),
            )
        )
    completeness = row.get("completeness")
    if completeness not in COVERAGE_VALUES:
        raise EvaluationContractError("invalid_answer_completeness")
    return AnswerJudgment(
        query_id=query_id,
        mode=mode,
        sentence_judgments=tuple(sentence_judgments),
        nugget_judgments=tuple(nugget_judgments),
        completeness=int(completeness),
        judge_model=judge_model,
        rubric_version=rubric_version,
        human_audit_status=human_audit_status,
    )


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise EvaluationContractError(
                f"invalid_jsonl:{path}:{line_number}"
            ) from error
        if not isinstance(row, dict):
            raise EvaluationContractError(
                f"jsonl_row_must_be_object:{path}:{line_number}"
            )
        rows.append(row)
    return rows


def evaluate_answer_item(
    query: EvaluationQuery,
    run: AnswerRun,
    judgment: AnswerJudgment,
) -> dict[str, Any]:
    if query.query_id != run.query_id or query.query_id != judgment.query_id:
        raise EvaluationContractError("answer_query_id_mismatch")
    if run.mode != judgment.mode:
        raise EvaluationContractError("answer_mode_mismatch")
    run_sentence_ids = {sentence.sentence_id for sentence in run.sentences}
    judgment_sentence_ids = {
        item.sentence_id for item in judgment.sentence_judgments
    }
    if run_sentence_ids != judgment_sentence_ids:
        raise EvaluationContractError("answer_sentence_judgments_incomplete")

    citation_ids = [
        chunk_id
        for sentence in run.sentences
        for chunk_id in sentence.citation_chunk_ids
    ]
    valid_citations = [
        chunk_id
        for chunk_id in citation_ids
        if chunk_id in run.evidence_chunk_ids
    ]
    relevant_chunk_ids = set(query.relevant_chunk_ids)
    relevant_citations = [
        chunk_id for chunk_id in citation_ids if chunk_id in relevant_chunk_ids
    ]
    judgment_by_sentence = {
        item.sentence_id: item for item in judgment.sentence_judgments
    }
    requiring_citation = [
        sentence
        for sentence in run.sentences
        if judgment_by_sentence[sentence.sentence_id].requires_citation
    ]
    cited_required_sentences = [
        sentence for sentence in requiring_citation if sentence.citation_chunk_ids
    ]
    support_scores = [
        judgment_by_sentence[sentence.sentence_id].support / 2
        for sentence in requiring_citation
    ]
    fully_supported = [
        judgment_by_sentence[sentence.sentence_id].support == 2
        for sentence in requiring_citation
    ]
    nugget_weights = [
        2 if nugget.importance == "vital" else 1
        for nugget in judgment.nugget_judgments
    ]
    nugget_weighted_coverage = (
        sum(
            weight * (nugget.coverage / 2)
            for nugget, weight in zip(
                judgment.nugget_judgments,
                nugget_weights,
                strict=True,
            )
        )
        / sum(nugget_weights)
        if nugget_weights
        else None
    )
    expected_refusal = query.answerability in {"partial", "none"}
    return {
        "query_id": query.query_id,
        "mode": run.mode,
        "course_id": query.course_id,
        "query_type": query.query_type,
        "answerability": query.answerability,
        "refused": run.refused,
        "expected_refusal": expected_refusal,
        "refusal_correct": run.refused == expected_refusal,
        "citation_validity": (
            len(valid_citations) / len(citation_ids) if citation_ids else None
        ),
        "citation_relevance": (
            len(relevant_citations) / len(citation_ids)
            if citation_ids
            else None
        ),
        "citation_completeness": (
            len(cited_required_sentences) / len(requiring_citation)
            if requiring_citation
            else None
        ),
        "sentence_support": mean(support_scores) if support_scores else None,
        "fully_supported_claim_rate": (
            sum(fully_supported) / len(fully_supported)
            if fully_supported
            else None
        ),
        "nugget_coverage": nugget_weighted_coverage,
        "answer_completeness": judgment.completeness / 2,
        "judge_model": judgment.judge_model,
        "rubric_version": judgment.rubric_version,
        "human_audit_status": judgment.human_audit_status,
    }


ANSWER_METRICS = (
    "refusal_correct",
    "citation_validity",
    "citation_relevance",
    "citation_completeness",
    "sentence_support",
    "fully_supported_claim_rate",
    "nugget_coverage",
    "answer_completeness",
)


def summarize_answer_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_mode: dict[str, Any] = {}
    for mode in sorted({str(row["mode"]) for row in rows}):
        mode_rows = [row for row in rows if row["mode"] == mode]
        metrics: dict[str, Any] = {"query_count": len(mode_rows)}
        for metric_name in ANSWER_METRICS:
            values = [
                float(row[metric_name])
                for row in mode_rows
                if row.get(metric_name) is not None
            ]
            metrics[metric_name] = (
                round(mean(values), 6) if values else None
            )
            metrics[f"{metric_name}_n"] = len(values)
        by_mode[mode] = metrics
    return {"by_mode": by_mode}


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    Path(path).write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
