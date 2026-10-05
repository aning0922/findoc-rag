"""本地两期收入确认：查证当前来源、绑定所见快照、持久读回后计算。

应用服务负责重新查证；快照摘要只是比较键，调用方自报版本不能代替查证。
不接入生产 Agent、不调用 LLM，也不定义第二套增长率公式。
"""

import asyncio
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import json
from typing import Literal, Protocol

from app.agent import revenue_extraction
from app.agent.financial_facts import FinancialFactRepository, FinancialUnit
from app.agent.research_workflow import (
    ConfirmedRevenueFact,
    RevenueCandidate,
    RevenueGrowthResult,
    RevenueWorkflowStage,
    begin_revenue_workflow,
    calculate_confirmed_revenue_growth,
    confirm_revenue_candidates,
    record_revenue_candidates,
)
from app.documents.models import DocumentRecord, DocumentStatus
from app.documents.ports import ObjectStore
from app.documents.preparation import DocumentReader


ConfirmationKind = Literal["local_operator", "simulated_test"]


class RevenueConfirmationError(RuntimeError):
    """确认/读回/计算被拒绝；只带稳定错误码，不带可用旧结果。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RevenueSourceRevision:
    """来源版本：服务端文档范围/内容/处理次数，以及当前抽取规则版本。"""

    workspace_id: str
    document_id: str
    content_sha256: str
    attempt: int
    extraction_method: str
    extraction_version: str


def candidate_payload(candidate: RevenueCandidate) -> dict[str, object]:
    """候选转可审阅 JSON；金额保存十进制字符串，全部原文证据保留。"""
    return {
        "workspace_id": candidate.workspace_id,
        "document_id": candidate.document_id,
        "source_ref": candidate.source_ref,
        "chunk_id": candidate.chunk_id,
        "source_file": candidate.source_file,
        "page": candidate.page,
        "period": candidate.period,
        "value": format(candidate.value, "f"),
        "unit": candidate.unit.value if candidate.unit is not None else None,
        "extraction_method": candidate.extraction_method,
        "extraction_version": candidate.extraction_version,
        "evidence": [asdict(item) for item in candidate.evidence],
    }


@dataclass(frozen=True)
class RevenueReview:
    """供操作者核对的一组不可变候选；摘要绑定版本与全部内容，不含检索分数。"""

    revision: RevenueSourceRevision
    candidates: tuple[RevenueCandidate, ...]

    def __post_init__(self) -> None:
        """复用候选准入，并收紧到有证据、人民币元、当前两期和明确抽取版本。"""
        revision = self.revision
        if (
            not revision.workspace_id.strip()
            or not revision.document_id.strip()
            or len(revision.content_sha256) != 64
            or any(char not in "0123456789abcdef" for char in revision.content_sha256)
            or isinstance(revision.attempt, bool)
            or not isinstance(revision.attempt, int)
            or revision.attempt < 1
            or not revision.extraction_method.strip()
            or not revision.extraction_version.strip()
        ):
            raise RevenueConfirmationError("source_invalid")
        state = record_revenue_candidates(
            begin_revenue_workflow(
                workspace_id=revision.workspace_id, document_id=revision.document_id
            ),
            self.candidates,
        )
        if state.stage is not RevenueWorkflowStage.AWAITING_CONFIRMATION:
            raise RevenueConfirmationError(str(state.failure_code))
        if len(self.candidates) != 2:
            raise RevenueConfirmationError("candidate_conflict")
        for item in self.candidates:
            if isinstance(item.period, bool) or not isinstance(item.period, int):
                raise RevenueConfirmationError("period_mismatch")
            if item.unit is not FinancialUnit.CNY_YUAN:
                raise RevenueConfirmationError("unit_conflict")
            if not item.evidence or any(e.source_file != item.source_file for e in item.evidence):
                raise RevenueConfirmationError("source_invalid")
            if (item.extraction_method, item.extraction_version) != (
                revision.extraction_method,
                revision.extraction_version,
            ):
                raise RevenueConfirmationError("source_changed")
        if len({item.source_ref for item in self.candidates}) != 2:
            raise RevenueConfirmationError("source_invalid")

    def to_payload(self) -> dict[str, object]:
        """输出版本和按期间排序的完整候选；调用方不得改写后直接保存。"""
        return {
            "schema": "revenue-review-v1",
            "revision": asdict(self.revision),
            "candidates": [
                candidate_payload(item) for item in sorted(self.candidates, key=lambda c: c.period)
            ],
        }

    @property
    def snapshot_id(self) -> str:
        """对完整可审阅内容生成稳定摘要；不拿 source_ref 充当来源版本。"""
        content = json.dumps(
            self.to_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RevenueConfirmation:
    """已保存的整组确认：操作者动作类型、原确认时间与完整所见快照。"""

    confirmation_id: str
    confirmed_at: datetime
    confirmation_kind: ConfirmationKind
    review: RevenueReview

    def confirmed_facts(self) -> tuple[ConfirmedRevenueFact, ...]:
        """从已读回候选复用原确认变体恢复事实；本方法不证明当前来源仍有效。"""
        state = record_revenue_candidates(
            begin_revenue_workflow(
                workspace_id=self.review.revision.workspace_id,
                document_id=self.review.revision.document_id,
            ),
            self.review.candidates,
        )
        return confirm_revenue_candidates(state).confirmed_facts


@dataclass(frozen=True)
class ConfirmedRevenueCalculation:
    """本次成功计算及其确认身份/版本；失败时不会构造此对象。"""

    confirmation: RevenueConfirmation
    result: RevenueGrowthResult

    def to_payload(self) -> dict[str, object]:
        """输出程序真值、两条输入及全部证据，不包含内部物理路径。"""
        return {
            "confirmation_id": self.confirmation.confirmation_id,
            "confirmed_at": self.confirmation.confirmed_at.isoformat(),
            "confirmation_kind": self.confirmation.confirmation_kind,
            "snapshot_id": self.confirmation.review.snapshot_id,
            "revision": asdict(self.confirmation.review.revision),
            "value": format(self.result.value, "f"),
            "unit": self.result.unit,
            "formula_id": self.result.formula_id,
            "inputs": [candidate_payload(item) for item in self.confirmation.review.candidates],
        }


class RevenueConfirmationRepository(Protocol):
    """整组保存/范围读回与本次计算的事实查询端口；不接收调用方裸金额。"""

    def save(
        self, *, review: RevenueReview, confirmation_kind: ConfirmationKind
    ) -> RevenueConfirmation: ...

    def load(
        self, *, confirmation_id: str, current_review: RevenueReview
    ) -> RevenueConfirmation: ...

    def fact_repository(
        self, *, confirmation_id: str, current_review: RevenueReview
    ) -> FinancialFactRepository: ...


class RevenueSourceReader:
    """每次从服务端文档、实际 PDF 和候选服务恢复当前可确认快照。"""

    def __init__(
        self,
        *,
        documents: DocumentReader,
        objects: ObjectStore,
        candidates: revenue_extraction.RevenueCandidateService,
    ) -> None:
        self._documents = documents
        self._objects = objects
        self._candidates = candidates

    async def _read_document(self, document_id: str) -> DocumentRecord:
        """核对当前 ready 和实际 PDF 摘要；文件或读取异常直接阻断。"""
        document = await self._documents.get_document(document_id)
        if document.status is not DocumentStatus.READY:
            raise RevenueConfirmationError("source_unavailable")
        content = await asyncio.to_thread(self._objects.read_bytes, document.object_key)
        if hashlib.sha256(content).hexdigest() != document.content_sha256:
            raise RevenueConfirmationError("source_changed")
        return document

    async def read(self, *, document_id: str) -> RevenueReview:
        """收集前后均查证文档；候选由当前代码重新获取，不从旧确认复制版本。"""
        before = await self._read_document(document_id)
        collected = await self._candidates.collect(document_id=document_id)
        after = await self._read_document(document_id)
        if before != after:
            raise RevenueConfirmationError("source_changed")
        state = collected.state
        if state.stage is not RevenueWorkflowStage.AWAITING_CONFIRMATION:
            raise RevenueConfirmationError(str(state.failure_code))
        return RevenueReview(
            revision=RevenueSourceRevision(
                workspace_id=after.workspace_id,
                document_id=after.document_id,
                content_sha256=after.content_sha256,
                attempt=after.attempt,
                extraction_method=revenue_extraction.EXTRACTION_METHOD,
                extraction_version=revenue_extraction.EXTRACTION_VERSION,
            ),
            candidates=state.candidates,
        )


class RevenueConfirmationService:
    """本地业务入口：展示→明确接受→整组保存→当前查证→持久事实计算。"""

    def __init__(
        self, *, source_reader: RevenueSourceReader, repository: RevenueConfirmationRepository
    ) -> None:
        self._source_reader = source_reader
        self._repository = repository

    async def preview(self, *, document_id: str) -> RevenueReview:
        """仅展示当前候选；不创建确认，也不计算。"""
        return await self._source_reader.read(document_id=document_id)

    async def confirm(
        self,
        *,
        document_id: str,
        reviewed_snapshot_id: str,
        accepted: bool,
        confirmation_kind: ConfirmationKind,
    ) -> RevenueConfirmation:
        """接受明确动作与所见摘要；重新收集完全一致才保存，两期不能部分接受。"""
        if accepted is not True:
            raise RevenueConfirmationError("confirmation_required")
        if confirmation_kind not in ("local_operator", "simulated_test"):
            raise RevenueConfirmationError("confirmation_required")
        current = await self._source_reader.read(document_id=document_id)
        if current.snapshot_id != reviewed_snapshot_id:
            raise RevenueConfirmationError("review_changed")
        return await asyncio.to_thread(
            self._repository.save, review=current, confirmation_kind=confirmation_kind
        )

    async def calculate(
        self, *, document_id: str, confirmation_id: str
    ) -> ConfirmedRevenueCalculation:
        """重新核证来源，从 SQLite 读回完整有效确认，调用原业务计算函数。"""
        current = await self._source_reader.read(document_id=document_id)
        confirmation = await asyncio.to_thread(
            self._repository.load, confirmation_id=confirmation_id, current_review=current
        )
        state = replace(
            begin_revenue_workflow(
                workspace_id=current.revision.workspace_id,
                document_id=current.revision.document_id,
            ),
            stage=RevenueWorkflowStage.READY_FOR_CALCULATION,
            confirmed_facts=confirmation.confirmed_facts(),
        )
        repository = self._repository.fact_repository(
            confirmation_id=confirmation_id, current_review=current
        )
        calculated = await asyncio.to_thread(
            calculate_confirmed_revenue_growth, state, repository=repository
        )
        if calculated.result is None:
            raise RevenueConfirmationError(str(calculated.failure_code))
        # 计算只产生一个新结果；返回前再次查证，变化时不把刚算出的值交给调用方。
        final_review = await self._source_reader.read(document_id=document_id)
        if final_review.snapshot_id != current.snapshot_id:
            raise RevenueConfirmationError("source_changed")
        return ConfirmedRevenueCalculation(confirmation, calculated.result)
