import json
from typing import Any

from experiments.day43_config import PROJECT_ROOT
from scripts.evaluate_day42_retrieval import load_questions


LEGACY_QUESTION_PATH = PROJECT_ROOT / "eval/day43_questions_v2.jsonl"
TRUSTED_RAG_QUESTION_PATH = PROJECT_ROOT / "eval/trusted_rag_questions_v1.jsonl"
V2_CHUNK_DIR = PROJECT_ROOT / "data/day43_data_v2"


def test_trusted_rag_question_set_preserves_frozen_cases_and_validates_new_evidence() -> None:
    """输入为原12题、正式20题和冻结Day43 v2 chunk；
    预期Q1～Q12内容完全不变，正式题集共20题且15题可回答、5题不可回答，
    所有case_id唯一，新可回答题的证据ID存在且metadata匹配，
    新不可回答题保存非空核证范围和核证依据；
    若数量、旧题内容、证据身份或不可回答核证字段不符合预期，
    说明正式题集的版本冻结与审计合同被破坏。
    """
    legacy_questions = load_questions(LEGACY_QUESTION_PATH)
    formal_questions = load_questions(TRUSTED_RAG_QUESTION_PATH)

    # 第一层：正式题集必须保留原12题，不得借扩题修改历史冻结样本。
    assert formal_questions[:12] == legacy_questions

    # 第二层：冻结总题数、可回答/不可回答比例和稳定case ID。
    assert len(formal_questions) == 20
    assert sum(question["answerable"] is True for question in formal_questions) == 15
    assert sum(question["answerable"] is False for question in formal_questions) == 5

    case_ids = [question["case_id"] for question in formal_questions]
    assert case_ids == [f"Q{number}" for number in range(1, 21)]
    assert len(case_ids) == len(set(case_ids))

    # 第三层：读取冻结v2数据，按chunk_id建立唯一证据索引。
    chunks_by_id: dict[str, dict[str, Any]] = {}

    chunk_paths = sorted(V2_CHUNK_DIR.glob("*_chunks.jsonl"))
    assert chunk_paths

    for chunk_path in chunk_paths:
        for line_number, line in enumerate(
            chunk_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue

            chunk = json.loads(line)
            assert isinstance(chunk, dict), (
                f"{chunk_path} 第{line_number}行必须是JSON对象"
            )

            chunk_id = chunk.get("chunk_id")
            assert isinstance(chunk_id, str) and chunk_id.strip(), (
                f"{chunk_path} 第{line_number}行缺少有效chunk_id"
            )
            assert chunk_id not in chunks_by_id, (
                f"冻结v2数据存在重复chunk_id：{chunk_id}"
            )

            chunks_by_id[chunk_id] = chunk

    questions_by_id = {
        question["case_id"]: question
        for question in formal_questions
    }

    # 第四层：Q13～Q17必须有答案要点和真实存在的冻结证据。
    for case_id in ("Q13", "Q14", "Q15", "Q16", "Q17"):
        question = questions_by_id[case_id]

        assert question["answerable"] is True

        answer_points = question.get("answer_points")
        assert isinstance(answer_points, list) and answer_points
        assert all(
            isinstance(answer_point, str) and answer_point.strip()
            for answer_point in answer_points
        )

        relevant_chunk_ids = question["relevant_chunk_ids"]
        expected_metadata = question["expected_metadata"]

        assert relevant_chunk_ids
        assert isinstance(expected_metadata, dict)
        assert set(relevant_chunk_ids) == set(expected_metadata)

        for chunk_id in relevant_chunk_ids:
            assert chunk_id in chunks_by_id, (
                f"{case_id}相关证据不存在：{chunk_id}"
            )

            actual_chunk = chunks_by_id[chunk_id]
            expected_chunk_metadata = expected_metadata[chunk_id]

            for field_name, expected_value in expected_chunk_metadata.items():
                assert actual_chunk.get(field_name) == expected_value, (
                    f"{case_id}证据{chunk_id}的{field_name}发生漂移："
                    f"expected={expected_value!r}, "
                    f"actual={actual_chunk.get(field_name)!r}"
                )

    # 第五层：Q18～Q20必须是经过限定范围核证的不可回答题。
    for case_id in ("Q18", "Q19", "Q20"):
        question = questions_by_id[case_id]

        assert question["answerable"] is False
        assert question["answer_points"] == []
        assert question["relevant_chunk_ids"] == []
        assert question["expected_metadata"] == {}

        verification_scope = question.get("verification_scope")
        verification_basis = question.get("verification_basis")

        assert isinstance(verification_scope, str)
        assert verification_scope.strip()

        assert isinstance(verification_basis, str)
        assert verification_basis.strip()