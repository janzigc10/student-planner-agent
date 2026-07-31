from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.rag import (
    RAG_BM25_CANDIDATE_K,
    RAG_EVIDENCE_CANDIDATE_K,
    RAG_RRF_K,
    RAG_VECTOR_CANDIDATE_K,
    HashEmbeddings,
    LocalRAGRetriever,
)
from app.agent.rag_corpus import CourseChunk, load_frozen_chunks
from app.agent.rag_evaluation import (
    DEFAULT_GATE_GRID,
    EvidenceRequirement,
    EvaluationContractError,
    EvaluationQuery,
    Qrel,
    build_challenge_manifest,
    dataset_sha256,
    load_evaluation_queries,
    validate_challenge_contract,
)
from app.config import settings


DATASET_VERSION = "rag-course-challenge-v1"
EVIDENCE_TIER = "llm_assisted_unreviewed"
POOL_MODES = (
    "embedding_only",
    "bm25_only",
    "hybrid_rrf",
    "hybrid_rerank",
)
POOL_TOP_K = 20
BLIND_ORDER_SEED = "course-rag-challenge-v1-blind-order"


@dataclass(frozen=True)
class ChallengeSpec:
    query_id: str
    query: str
    course_id: str
    query_type: str
    answerability: str
    topic_keys: tuple[str, ...]
    reference_answer: str
    expected_terms: tuple[str, ...]


CHALLENGE_SPECS = (
    ChallengeSpec(
        "challenge-ml-01",
        "梯度下降里的“步子迈得太大”具体指什么，为什么它会让损失在低点附近反复越过去？",
        "machine_learning",
        "exact_entity",
        "full",
        ("gradient_descent",),
        "步子大小由学习率控制；学习率过大可能越过低损失区域并产生震荡，过小则收敛缓慢。",
        ("梯度下降", "学习率", "震荡", "收敛"),
    ),
    ChallengeSpec(
        "challenge-ml-02",
        "有人说支持向量机只是在训练样本里找一条分界线。请用资料纠正这个说法，并解释支持向量和核方法各自做什么。",
        "machine_learning",
        "paraphrase",
        "full",
        ("svm",),
        "支持向量机寻找最大间隔分类边界，边界主要由支持向量决定；核方法可把非线性问题映射到更适合分离的空间。",
        ("最大间隔", "支持向量", "核方法"),
    ),
    ChallengeSpec(
        "challenge-ml-03",
        "同样写成一个数值输出，线性回归和逻辑回归的学习目标为什么不同？请从输出含义、损失思路和适用任务比较。",
        "machine_learning",
        "comparison",
        "full",
        ("linear_regression", "logistic_regression"),
        "线性回归预测连续值并拟合数值关系；逻辑回归通过概率映射解决分类问题。两者输出语义和损失目标不同，不能因名称相近而混用。",
        ("连续值", "概率", "分类", "线性回归", "逻辑回归"),
    ),
    ChallengeSpec(
        "challenge-ml-04",
        "我先在全部样本上挑出最有用的特征，再划训练集和测试集，这样评估为什么可能虚高？请把数据划分和特征工程连起来说明。",
        "machine_learning",
        "multi_concept",
        "full",
        ("dataset_split", "feature_engineering"),
        "测试集应只用于最终评估。若在划分前利用全部数据选择特征，测试信息会泄漏到训练流程，使评估偏乐观；特征处理应在训练数据内拟合并一致应用。",
        ("测试集", "特征工程", "数据泄漏", "评估"),
    ),
    ChallengeSpec(
        "challenge-ml-05",
        "概括类别极不平衡时为什么不能只报准确率，并说明混淆矩阵、精确率、召回率和 F1 分别怎样帮助判断。",
        "machine_learning",
        "summary",
        "full",
        ("classification_metrics",),
        "准确率可能掩盖少数类失败。混淆矩阵给出 TP、FP、TN、FN，精确率关注预测正例的可信度，召回率关注真实正例的找回程度，F1 平衡精确率与召回率。",
        ("准确率", "混淆矩阵", "精确率", "召回率", "F1"),
    ),
    ChallengeSpec(
        "challenge-ml-06",
        "请先根据资料解释 K-means 怎样反复更新簇中心，再给出我校 2027 年这道题的评分细则和老师尚未公布的标准答案。",
        "machine_learning",
        "long_student_query",
        "partial",
        ("clustering",),
        "资料可说明 K-means 通过分配样本与更新簇中心迭代优化，但不包含未来考试评分细则或未公布的标准答案。",
        ("K-means", "簇中心", "迭代"),
    ),
    ChallengeSpec(
        "challenge-ml-07",
        "只根据这套机器学习复习资料，告诉我明天学校 GPU 服务器每小时的实时排队人数。",
        "machine_learning",
        "out_of_scope",
        "none",
        (),
        "",
        (),
    ),
    ChallengeSpec(
        "challenge-cn-01",
        "社会主义改造完成后，所有制结构发生了什么关键变化，它和中华人民共和国成立是不是同一件事？",
        "modern_chinese_history",
        "exact_entity",
        "full",
        ("socialist_transformation", "founding_prc"),
        "中华人民共和国成立标志新中国建立；社会主义改造则推动生产资料私有制向社会主义公有制转变。两者时间、任务和制度意义不同。",
        ("中华人民共和国成立", "社会主义改造", "公有制"),
    ),
    ChallengeSpec(
        "challenge-cn-02",
        "把改革开放说成“只是恢复旧市场”哪里不准确？请用资料解释它怎样调整发展路径。",
        "modern_chinese_history",
        "paraphrase",
        "full",
        ("reform_opening",),
        "改革开放是在社会主义制度基础上解放和发展生产力，通过体制改革与对外开放调整发展路径，不是简单恢复旧制度。",
        ("改革开放", "体制改革", "对外开放", "生产力"),
    ),
    ChallengeSpec(
        "challenge-cn-03",
        "洋务运动和戊戌维新都主张学习西方，但二者想改到哪一层、采取什么办法、为什么不能混为一谈？",
        "modern_chinese_history",
        "comparison",
        "full",
        ("westernization", "reform1898"),
        "洋务运动侧重器物和近代工业建设，未根本改变封建制度；戊戌维新进一步主张政治制度改革。二者改革层次、主体和路径不同。",
        ("洋务运动", "戊戌维新", "器物", "制度改革"),
    ),
    ChallengeSpec(
        "challenge-cn-04",
        "从思想启蒙到群众运动再到新型政党建立：新文化运动、五四运动和中国共产党成立之间应怎样串联，又有哪些边界不能写成简单因果？",
        "modern_chinese_history",
        "multi_concept",
        "full",
        ("new_culture", "may_fourth", "cpc_founding"),
        "新文化运动推动思想启蒙，五四运动促进马克思主义传播并形成新的社会动员，中国共产党成立具有相应思想和干部条件；三者有历史联系，但不能写成单一、自动的因果链。",
        ("新文化运动", "五四运动", "中国共产党成立", "马克思主义"),
    ),
    ChallengeSpec(
        "challenge-cn-05",
        "概括全民族抗战形成、主要力量和历史意义，并指出为什么不能把胜利归因于单一战场或单一力量。",
        "modern_chinese_history",
        "summary",
        "full",
        ("anti_japanese",),
        "全民族抗战是在民族危机下形成的广泛动员，正面战场、敌后战场和社会各界共同作用；胜利是多种力量长期协同的结果。",
        ("全民族抗战", "正面战场", "敌后战场", "共同作用"),
    ),
    ChallengeSpec(
        "challenge-cn-06",
        "请依据资料说明辛亥革命结束了什么、又没有完成什么，然后附上 2027 年本校命题教师准备采用的原题。",
        "modern_chinese_history",
        "long_student_query",
        "partial",
        ("xinhai",),
        "资料可说明辛亥革命结束君主专制制度并建立共和，但没有完成反帝反封建任务；资料不包含未来未公开原题。",
        ("辛亥革命", "君主专制", "共和", "反帝反封建"),
    ),
    ChallengeSpec(
        "challenge-cn-07",
        "根据中国近现代史复习资料，查询本周末当地历史博物馆每个展厅的实时排队时长。",
        "modern_chinese_history",
        "out_of_scope",
        "none",
        (),
        "",
        (),
    ),
    ChallengeSpec(
        "challenge-world-01",
        "1929—1933 年经济危机为什么会从局部市场问题扩散成广泛危机？材料给出的机制链是什么？",
        "world_modern_history",
        "exact_entity",
        "full",
        ("great_depression",),
        "生产与消费失衡、金融体系脆弱和市场恐慌相互放大，使危机跨行业、跨地区扩散，并带来失业和社会动荡。",
        ("生产过剩", "金融", "失业", "扩散"),
    ),
    ChallengeSpec(
        "challenge-world-02",
        "“冷战就是完全没有战争”这句话为什么站不住？请换一种说法解释它的竞争方式和边界。",
        "world_modern_history",
        "paraphrase",
        "full",
        ("cold_war",),
        "冷战指美苏没有直接全面战争，但通过政治、经济、军事集团、军备竞赛和代理冲突展开长期对抗，因此不是没有战争或冲突。",
        ("冷战", "美苏", "军备竞赛", "代理冲突"),
    ),
    ChallengeSpec(
        "challenge-world-03",
        "杜鲁门主义和马歇尔计划都服务于美国冷战战略，但一个偏政治宣示、一个偏经济援助，这样比较还缺哪些目标与作用差异？",
        "world_modern_history",
        "comparison",
        "full",
        ("truman_doctrine", "marshall_plan"),
        "杜鲁门主义以遏制共产主义为政治战略宣示；马歇尔计划通过经济援助恢复西欧并巩固美国影响。二者手段不同但共同服务于冷战遏制战略。",
        ("杜鲁门主义", "马歇尔计划", "遏制", "经济援助"),
    ),
    ChallengeSpec(
        "challenge-world-04",
        "把杜鲁门主义、马歇尔计划、北约与华约放到同一条冷战升级链里：它们分别对应政治、经济和军事的哪一环？",
        "world_modern_history",
        "multi_concept",
        "full",
        ("truman_doctrine", "marshall_plan", "nato_warsaw"),
        "杜鲁门主义确立政治遏制方向，马歇尔计划提供经济手段，北约与华约形成对立军事集团，体现冷战由政策宣示走向制度化阵营对抗。",
        ("杜鲁门主义", "马歇尔计划", "北约", "华约"),
    ),
    ChallengeSpec(
        "challenge-world-05",
        "用“爆发—转折—国际合作—战后秩序”四个节点概括第二次世界大战，并说明材料提醒避免哪些单线叙事。",
        "world_modern_history",
        "summary",
        "full",
        ("world_war_two", "united_nations"),
        "二战由法西斯侵略扩张引发，多个战场和反法西斯力量共同推动转折与胜利，战时合作也促成联合国及战后秩序；不能只用单一战场解释全局。",
        ("第二次世界大战", "转折", "反法西斯", "联合国"),
    ),
    ChallengeSpec(
        "challenge-world-06",
        "先说明亚非拉民族解放运动为何在战后高涨，再列出截至 2027 年新增独立国家的实时完整名单和最新人口。",
        "world_modern_history",
        "long_student_query",
        "partial",
        ("decolonization",),
        "资料可解释殖民体系削弱、民族意识增强和国际环境变化推动战后民族解放运动，但不含截至未来日期的实时国家与人口数据。",
        ("民族解放", "殖民体系", "民族意识"),
    ),
    ChallengeSpec(
        "challenge-world-07",
        "用世界现代史课程资料计算下周美元兑人民币每天收盘价，并保证误差小于 0.1%。",
        "world_modern_history",
        "out_of_scope",
        "none",
        (),
        "",
        (),
    ),
    ChallengeSpec(
        "challenge-pol-01",
        "全过程人民民主中的“全过程”具体覆盖哪些环节，为什么不能只用投票次数衡量？",
        "political_theory",
        "exact_entity",
        "full",
        ("whole_process_democracy",),
        "全过程人民民主贯通选举、协商、决策、管理和监督等环节，强调广泛持续参与与实际治理效果，不能缩减为单次投票。",
        ("全过程人民民主", "选举", "协商", "监督"),
    ),
    ChallengeSpec(
        "challenge-pol-02",
        "共同富裕是不是要求所有人的收入和生活方式完全一样？请用资料中的目标与边界重新解释。",
        "political_theory",
        "paraphrase",
        "full",
        ("common_prosperity",),
        "共同富裕强调发展成果更公平惠及人民、缩小不合理差距，并非平均主义或所有人收入完全相同。",
        ("共同富裕", "公平", "差距", "平均主义"),
    ),
    ChallengeSpec(
        "challenge-pol-03",
        "人民代表大会和人民政协都讨论公共事务，但二者在国家权力、履职方式和制度定位上有什么根本区别？",
        "political_theory",
        "comparison",
        "full",
        ("peoples_congress", "cppcc"),
        "人民代表大会是国家权力机关，依法行使立法、决定、任免和监督等职权；人民政协是爱国统一战线组织，主要履行政治协商、民主监督和参政议政职能。",
        ("人民代表大会", "人民政协", "国家权力机关", "政治协商"),
    ),
    ChallengeSpec(
        "challenge-pol-04",
        "如果一个项目追求增长却造成高污染，怎样同时用新发展理念和生态文明建设判断它的问题，而不是只贴“绿色”标签？",
        "political_theory",
        "multi_concept",
        "full",
        ("new_development", "ecological_civilization"),
        "新发展理念要求创新、协调、绿色、开放、共享，生态文明强调尊重自然并把环境约束纳入发展决策；高污染增长违背绿色和可持续要求。",
        ("新发展理念", "生态文明", "绿色", "可持续"),
    ),
    ChallengeSpec(
        "challenge-pol-05",
        "概括全面依法治国与宪法权威的关系：为什么既要依法规范公权力，也不能把法治理解成只有惩罚？",
        "political_theory",
        "summary",
        "full",
        ("rule_of_law", "constitution"),
        "全面依法治国以宪法为根本依据，要求科学立法、严格执法、公正司法和全民守法，并通过制度规范公权力、保障权利；法治不只是惩罚。",
        ("依法治国", "宪法", "公权力", "权利"),
    ),
    ChallengeSpec(
        "challenge-pol-06",
        "请先说明文化自信为什么不等于排斥外来文化，再给出 2027 年各短视频平台文化类内容的实时热度排名。",
        "political_theory",
        "long_student_query",
        "partial",
        ("cultural_confidence",),
        "资料可说明文化自信建立在对自身文化价值的认同上，并可在交流互鉴中发展，不等于封闭排外；资料不含未来平台实时排名。",
        ("文化自信", "交流互鉴", "开放"),
    ),
    ChallengeSpec(
        "challenge-pol-07",
        "根据思想政治理论复习资料，告诉我明早 8 点经过学校东门的每辆公交车实时到站秒数。",
        "political_theory",
        "out_of_scope",
        "none",
        (),
        "",
        (),
    ),
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _artifact_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def build_frozen_config(corpus_manifest_sha256: str) -> dict[str, Any]:
    gate_grid = [dict(row) for row in DEFAULT_GATE_GRID]
    return {
        "schema_version": "course-rag-frozen-config-v1",
        "corpus_manifest_sha256": corpus_manifest_sha256,
        "retrieval_modes": list(POOL_MODES),
        "embedding": {
            "provider": "dashscope",
            "model": "text-embedding-v4",
            "dimensions": 1024,
        },
        "vector_store_provider": "chroma",
        "vector_candidate_top_k": RAG_VECTOR_CANDIDATE_K,
        "bm25_candidate_top_k": RAG_BM25_CANDIDATE_K,
        "rrf_k": RAG_RRF_K,
        "reranker": {
            "provider": "qwen3",
            "model": "qwen3-rerank",
            "candidate_top_k": RAG_EVIDENCE_CANDIDATE_K * 2,
        },
        "evaluation_top_k": 10,
        "answer_context_top_k": 3,
        "formal_reranker_fallback": False,
        "evidence_gate": {
            "calibration_data": "main_dataset_development_only",
            "selection_rule": (
                "minimize false_accept_rate under the evaluator contract, "
                "then maximize full_answer_recall"
            ),
            "selected_config_available_before_holdout_run": True,
            "parameter_grid": gate_grid,
            "parameter_grid_sha256": _sha256_bytes(
                _canonical_json_bytes(gate_grid)
            ),
        },
        "challenge_policy": {
            "used_for_tuning": False,
            "formal_runs_allowed": 1,
        },
    }


def _chunks_by_topic(
    chunks: Iterable[CourseChunk],
) -> dict[tuple[str, str], list[CourseChunk]]:
    result: dict[tuple[str, str], list[CourseChunk]] = {}
    for chunk in chunks:
        key = (
            str(chunk.metadata.get("course_id") or ""),
            str(chunk.metadata.get("chapter_id") or ""),
        )
        result.setdefault(key, []).append(chunk)
    return result


def _rank_topic_chunks(
    chunks: list[CourseChunk],
    expected_terms: tuple[str, ...],
) -> list[CourseChunk]:
    if not chunks:
        raise EvaluationContractError("challenge_topic_has_no_chunks")
    return sorted(
        chunks,
        key=lambda chunk: (
            -sum(
                term.casefold() in chunk.text.casefold()
                for term in expected_terms
            ),
            -sum(
                chunk.text.casefold().count(term.casefold())
                for term in expected_terms
            ),
            chunk.chunk_index,
            chunk.chunk_id,
        ),
    )


def _hit_chunk_id(hit: dict[str, Any]) -> str:
    metadata = dict(hit.get("metadata") or {})
    return str(hit.get("chunk_id") or metadata.get("chunk_id") or "")


def build_candidate_pool(
    specs: Iterable[ChallengeSpec],
    *,
    corpus_dir: Path,
    chunks: list[CourseChunk],
) -> dict[str, list[dict[str, Any]]]:
    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    chunks_by_topic = _chunks_by_topic(chunks)
    old_vector_provider = settings.rag_vector_store_provider
    old_reranker_key = settings.rag_reranker_api_key
    old_reranker_url = settings.rag_reranker_base_url
    settings.rag_vector_store_provider = "memory"
    settings.rag_reranker_api_key = ""
    settings.rag_reranker_base_url = ""
    try:
        retriever = LocalRAGRetriever(corpus_dir, embeddings=HashEmbeddings())
        pools: dict[str, list[dict[str, Any]]] = {}
        for spec in specs:
            candidates: dict[str, dict[str, Any]] = {}
            for mode in POOL_MODES:
                hits = retriever.retrieve(
                    spec.query,
                    top_k=POOL_TOP_K,
                    mode=mode,
                    allow_reranker_fallback=True,
                )
                for rank, hit in enumerate(hits, 1):
                    chunk_id = _hit_chunk_id(hit)
                    if not chunk_id or chunk_id not in chunk_by_id:
                        continue
                    candidate = candidates.setdefault(
                        chunk_id,
                        {
                            "query_id": spec.query_id,
                            "chunk_id": chunk_id,
                            "origins": [],
                        },
                    )
                    candidate["origins"].append(
                        {
                            "mode": mode,
                            "rank": rank,
                            "score": hit.get("score"),
                            "rerank_score": hit.get("rerank_score"),
                        }
                    )
            for topic_key in spec.topic_keys:
                topic_chunks = chunks_by_topic.get((spec.course_id, topic_key), [])
                for rank, seeded_chunk in enumerate(
                    _rank_topic_chunks(topic_chunks, spec.expected_terms)[:3],
                    1,
                ):
                    candidate = candidates.setdefault(
                        seeded_chunk.chunk_id,
                        {
                            "query_id": spec.query_id,
                            "chunk_id": seeded_chunk.chunk_id,
                            "origins": [],
                        },
                    )
                    candidate["origins"].append(
                        {"mode": "author_seed", "rank": rank, "score": None}
                    )
            rows: list[dict[str, Any]] = []
            for chunk_id, candidate in candidates.items():
                chunk = chunk_by_id[chunk_id]
                rows.append(
                    {
                        **candidate,
                        "source_id": chunk.source_id,
                        "course_id": str(chunk.metadata.get("course_id") or ""),
                        "chapter_id": str(chunk.metadata.get("chapter_id") or ""),
                        "text": chunk.text,
                    }
                )
            pools[spec.query_id] = sorted(rows, key=lambda row: row["chunk_id"])
        return pools
    finally:
        settings.rag_vector_store_provider = old_vector_provider
        settings.rag_reranker_api_key = old_reranker_key
        settings.rag_reranker_base_url = old_reranker_url


def build_challenge_queries(
    specs: Iterable[ChallengeSpec],
    *,
    chunks: list[CourseChunk],
    candidate_pools: dict[str, list[dict[str, Any]]],
) -> list[EvaluationQuery]:
    chunks_by_topic = _chunks_by_topic(chunks)
    queries: list[EvaluationQuery] = []
    for spec in specs:
        graded_by_topic: dict[str, list[CourseChunk]] = {}
        relevant_sources: list[str] = []
        for topic_key in spec.topic_keys:
            topic_chunks = chunks_by_topic.get((spec.course_id, topic_key), [])
            graded = _rank_topic_chunks(topic_chunks, spec.expected_terms)[:3]
            graded_by_topic[topic_key] = graded
            relevant_sources.append(graded[0].source_id)
        primary_ids = {
            graded[0].chunk_id for graded in graded_by_topic.values()
        }
        secondary_ids = {
            chunk.chunk_id
            for graded in graded_by_topic.values()
            for chunk in graded[1:]
        }
        qrels: list[Qrel] = []
        for candidate in candidate_pools[spec.query_id]:
            relevance = 0
            if spec.answerability != "none":
                if candidate["chunk_id"] in primary_ids:
                    relevance = 1 if spec.answerability == "partial" else 2
                elif candidate["chunk_id"] in secondary_ids:
                    relevance = 1
            qrels.append(Qrel(candidate["chunk_id"], relevance))
        requirements = ()
        if spec.answerability == "full":
            requirements = tuple(
                EvidenceRequirement(
                    requirement_id=f"topic_{topic_key}",
                    any_of_chunk_ids=(graded_by_topic[topic_key][0].chunk_id,),
                )
                for topic_key in spec.topic_keys
            )
        queries.append(
            EvaluationQuery(
                query_id=spec.query_id,
                query=spec.query,
                course_id=spec.course_id,
                query_type=spec.query_type,
                answerability=spec.answerability,
                reference_answer=spec.reference_answer,
                relevant_source_ids=tuple(relevant_sources),
                qrels=tuple(qrels),
                evidence_requirements=requirements,
                expected_terms=spec.expected_terms,
                split="holdout",
            )
        )
    return queries


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _review_id(query_id: str, chunk_id: str = "") -> str:
    digest = hashlib.sha256(f"{query_id}\0{chunk_id}".encode("utf-8")).hexdigest()
    return f"review-{digest[:16]}"


def _blind_sort_key(query_id: str, chunk_id: str) -> str:
    return hashlib.sha256(
        f"{BLIND_ORDER_SEED}\0{query_id}\0{chunk_id}".encode("utf-8")
    ).hexdigest()


def write_review_artifacts(
    output_dir: Path,
    *,
    specs: tuple[ChallengeSpec, ...],
    queries: list[EvaluationQuery],
    candidate_pools: dict[str, list[dict[str, Any]]],
) -> dict[str, Path]:
    query_by_id = {query.query_id: query for query in queries}
    query_review_path = output_dir / "blind_query_review.tsv"
    with query_review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "review_query_id",
                "course_id",
                "query",
                "answerability_full_partial_none",
                "review_notes",
            ),
            delimiter="\t",
        )
        writer.writeheader()
        for spec in specs:
            writer.writerow(
                {
                    "review_query_id": _review_id(spec.query_id),
                    "course_id": spec.course_id,
                    "query": spec.query,
                    "answerability_full_partial_none": "",
                    "review_notes": "",
                }
            )

    candidate_rows: list[dict[str, Any]] = []
    review_key: dict[str, Any] = {"queries": {}, "candidates": {}}
    for spec in specs:
        query = query_by_id[spec.query_id]
        review_query_id = _review_id(spec.query_id)
        review_key["queries"][review_query_id] = {
            "query_id": spec.query_id,
            "answerability": spec.answerability,
            "reference_answer": spec.reference_answer,
        }
        relevance_by_chunk = {
            qrel.chunk_id: qrel.relevance for qrel in query.qrels
        }
        for candidate in sorted(
            candidate_pools[spec.query_id],
            key=lambda row: _blind_sort_key(spec.query_id, row["chunk_id"]),
        ):
            review_id = _review_id(spec.query_id, candidate["chunk_id"])
            candidate_rows.append(
                {
                    "review_id": review_id,
                    "review_query_id": review_query_id,
                    "query": spec.query,
                    "candidate_text": candidate["text"],
                    "relevance_0_1_2": "",
                    "review_notes": "",
                }
            )
            review_key["candidates"][review_id] = {
                "query_id": spec.query_id,
                "chunk_id": candidate["chunk_id"],
                "source_id": candidate["source_id"],
                "provisional_relevance": relevance_by_chunk[candidate["chunk_id"]],
            }

    qrel_review_path = output_dir / "blind_qrel_review.tsv"
    with qrel_review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=tuple(candidate_rows[0]),
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(candidate_rows)

    judge_input_path = output_dir / "blind_judge_input.jsonl"
    _write_jsonl(
        judge_input_path,
        (
            {
                "review_id": row["review_id"],
                "review_query_id": row["review_query_id"],
                "query": row["query"],
                "candidate_text": row["candidate_text"],
                "rubric": (
                    "0=不能帮助回答；1=背景或部分证据；"
                    "2=直接回答核心信息。只根据给定文本判断。"
                ),
            }
            for row in candidate_rows
        ),
    )

    review_key_path = output_dir / "review_key.json"
    review_key_path.write_bytes(_canonical_json_bytes(review_key))
    return {
        "blind_query_review": query_review_path,
        "blind_qrel_review": qrel_review_path,
        "blind_judge_input": judge_input_path,
        "review_key": review_key_path,
    }


def generate_challenge(
    *,
    corpus_dir: Path,
    main_dataset_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise EvaluationContractError("challenge_output_directory_must_be_empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    corpus_manifest, chunks = load_frozen_chunks(corpus_dir)
    main_queries = load_evaluation_queries(main_dataset_path)
    main_ids = {query.query_id for query in main_queries}
    main_texts = {query.query.strip().casefold() for query in main_queries}
    if any(spec.query_id in main_ids for spec in CHALLENGE_SPECS):
        raise EvaluationContractError("challenge_query_id_overlaps_main")
    if any(spec.query.strip().casefold() in main_texts for spec in CHALLENGE_SPECS):
        raise EvaluationContractError("challenge_query_text_overlaps_main")

    frozen_config = build_frozen_config(corpus_manifest["manifest_sha256"])
    frozen_config_path = output_dir / "frozen_config.json"
    frozen_config_path.write_bytes(_canonical_json_bytes(frozen_config))
    frozen_config_sha256 = _artifact_sha256(frozen_config_path)

    candidate_pools = build_candidate_pool(
        CHALLENGE_SPECS,
        corpus_dir=corpus_dir,
        chunks=chunks,
    )
    queries = build_challenge_queries(
        CHALLENGE_SPECS,
        chunks=chunks,
        candidate_pools=candidate_pools,
    )
    challenge_path = output_dir / "challenge_queries.jsonl"
    _write_jsonl(challenge_path, (query.to_json() for query in queries))

    pool_path = output_dir / "candidate_pool.jsonl"
    _write_jsonl(
        pool_path,
        (
            candidate
            for spec in CHALLENGE_SPECS
            for candidate in candidate_pools[spec.query_id]
        ),
    )
    review_paths = write_review_artifacts(
        output_dir,
        specs=CHALLENGE_SPECS,
        queries=queries,
        candidate_pools=candidate_pools,
    )

    manifest = build_challenge_manifest(
        queries,
        dataset_version=DATASET_VERSION,
        corpus_manifest_sha256=corpus_manifest["manifest_sha256"],
        evidence_tier=EVIDENCE_TIER,
        frozen_config_sha256=frozen_config_sha256,
    )
    manifest.update(
        {
            "synthetic": True,
            "annotation_method": (
                "model-authored challenge query specifications plus deterministic "
                "source-truth provisional qrels over a local four-mode Top-20 pool"
            ),
            "human_review_status": "not_reviewed",
            "main_dataset_sha256": dataset_sha256(main_queries),
            "pooling": {
                "modes": list(POOL_MODES),
                "top_k_per_mode": POOL_TOP_K,
                "embedding_for_pool_construction": "local_hash",
                "hybrid_rerank_for_pool_construction": "local_feature_fallback",
                "author_seed_relevant_chunks": True,
                "candidate_count": sum(len(rows) for rows in candidate_pools.values()),
            },
            "artifacts": {
                "frozen_config.json": frozen_config_sha256,
                "challenge_queries.jsonl": _artifact_sha256(challenge_path),
                "candidate_pool.jsonl": _artifact_sha256(pool_path),
                **{
                    path.name: _artifact_sha256(path)
                    for path in review_paths.values()
                },
            },
        }
    )
    manifest_path = output_dir / "challenge_manifest.json"
    manifest_path.write_bytes(_canonical_json_bytes(manifest))

    validation = validate_challenge_contract(
        queries,
        main_queries=main_queries,
        challenge_manifest=manifest,
        corpus_manifest_sha256=corpus_manifest["manifest_sha256"],
        known_chunk_ids={chunk.chunk_id for chunk in chunks},
        known_source_ids={chunk.source_id for chunk in chunks},
    )
    return {
        **validation,
        "output_dir": str(output_dir.resolve()),
        "qrel_count": sum(len(query.qrels) for query in queries),
        "candidate_count": manifest["pooling"]["candidate_count"],
        "human_review_status": manifest["human_review_status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create the untouched 28-query course RAG challenge holdout, "
            "four-mode candidate pool, and blind review artifacts."
        )
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("data/rag/course_v1"),
    )
    parser.add_argument(
        "--main-dataset",
        type=Path,
        default=Path("data/rag/course_v1/golden_queries.jsonl"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/rag/course_challenge_v1"),
    )
    args = parser.parse_args()
    result = generate_challenge(
        corpus_dir=args.corpus_dir,
        main_dataset_path=args.main_dataset,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
