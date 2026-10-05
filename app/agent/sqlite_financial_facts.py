"""两期收入的最小 SQLite 确认仓储，复用现有 FinancialFactRepository。

与 documents 共用一个数据库；确认头和两条事实整组提交。历史确认不删除，
但读取时必须提供应用服务刚查证的完整快照，并核对数据库中的当前文档。
"""

from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import uuid

from app.agent.financial_facts import FinancialFact, FinancialFactKey, FinancialFactRepository
from app.agent.research_workflow import RevenueCandidate, RevenueEvidence
from app.agent.financial_facts import FinancialUnit
from app.agent.revenue_confirmation import (
    ConfirmationKind,
    RevenueConfirmation,
    RevenueConfirmationError,
    RevenueReview,
    RevenueSourceRevision,
)
from app.agent.tool_loop import ToolExecutionContext


class SQLiteRevenueConfirmationRepository:
    """保存明确确认，按本次服务端范围/版本读回完整两期；不保存计算结果。"""

    def __init__(self, database_path: Path) -> None:
        """绑定已有文档库并增量建两表，不迁移或覆盖历史业务数据。"""
        self._database_path = database_path
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS revenue_confirmations (
                    confirmation_id TEXT PRIMARY KEY,
                    snapshot_id TEXT NOT NULL UNIQUE,
                    workspace_id TEXT NOT NULL,
                    document_id TEXT NOT NULL REFERENCES documents(document_id),
                    content_sha256 TEXT NOT NULL,
                    attempt INTEGER NOT NULL CHECK (attempt >= 1),
                    extraction_method TEXT NOT NULL,
                    extraction_version TEXT NOT NULL,
                    confirmed_at TEXT NOT NULL,
                    confirmation_kind TEXT NOT NULL
                        CHECK (confirmation_kind IN ('local_operator', 'simulated_test'))
                );
                CREATE TABLE IF NOT EXISTS confirmed_revenue_facts (
                    confirmation_id TEXT NOT NULL
                        REFERENCES revenue_confirmations(confirmation_id),
                    fact_key TEXT NOT NULL CHECK (fact_key = 'revenue'),
                    period INTEGER NOT NULL CHECK (period IN (2024, 2025)),
                    source_ref TEXT NOT NULL,
                    value_text TEXT NOT NULL CHECK (typeof(value_text) = 'text'),
                    unit TEXT NOT NULL CHECK (unit = 'CNY_YUAN'),
                    chunk_id TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    page INTEGER NOT NULL CHECK (page >= 1),
                    evidence_json TEXT NOT NULL,
                    PRIMARY KEY (confirmation_id, period),
                    UNIQUE (confirmation_id, source_ref)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        """每次创建短连接，启用外键；连接由调用方关闭。"""
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _check_document(connection: sqlite3.Connection, review: RevenueReview) -> None:
        """在当前事务中核对文档状态和版本，防止查证后官方状态已变化。"""
        revision = review.revision
        row = connection.execute(
            "SELECT workspace_id, content_sha256, attempt, status FROM documents "
            "WHERE document_id = ?",
            (revision.document_id,),
        ).fetchone()
        if row is None or (
            row["workspace_id"],
            row["content_sha256"],
            row["attempt"],
            row["status"],
        ) != (revision.workspace_id, revision.content_sha256, revision.attempt, "ready"):
            raise RevenueConfirmationError("source_changed")

    def save(
        self, *, review: RevenueReview, confirmation_kind: ConfirmationKind
    ) -> RevenueConfirmation:
        """事务保存整组确认；相同有效快照返回原记录，任一写入失败全部回滚。"""
        if confirmation_kind not in ("local_operator", "simulated_test"):
            raise RevenueConfirmationError("confirmation_required")
        revision = review.revision
        with closing(self._connect()) as connection:
            with connection:
                # 在同库锁定写事务，先核对文档，再写确认头和两条事实。
                connection.execute("BEGIN IMMEDIATE")
                self._check_document(connection, review)
                existing = connection.execute(
                    "SELECT confirmation_id FROM revenue_confirmations WHERE snapshot_id = ?",
                    (review.snapshot_id,),
                ).fetchone()
                if existing is not None:
                    confirmation = self._load(connection, str(existing["confirmation_id"]), review)
                    if confirmation.confirmation_kind != confirmation_kind:
                        raise RevenueConfirmationError("confirmation_kind_mismatch")
                    return confirmation
                confirmation_id = str(uuid.uuid4())
                confirmed_at = datetime.now(UTC)
                connection.execute(
                    "INSERT INTO revenue_confirmations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        confirmation_id,
                        review.snapshot_id,
                        revision.workspace_id,
                        revision.document_id,
                        revision.content_sha256,
                        revision.attempt,
                        revision.extraction_method,
                        revision.extraction_version,
                        confirmed_at.isoformat(),
                        confirmation_kind,
                    ),
                )
                for candidate in sorted(review.candidates, key=lambda item: item.period):
                    evidence = [
                        {
                            "chunk_id": item.chunk_id,
                            "source_file": item.source_file,
                            "page": item.page,
                            "text": item.text,
                            "start": item.start,
                            "end": item.end,
                            "raw_value": item.raw_value,
                            "raw_unit": item.raw_unit,
                        }
                        for item in candidate.evidence
                    ]
                    connection.execute(
                        "INSERT INTO confirmed_revenue_facts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            confirmation_id,
                            "revenue",
                            candidate.period,
                            candidate.source_ref,
                            format(candidate.value, "f"),
                            "CNY_YUAN",
                            candidate.chunk_id,
                            candidate.source_file,
                            candidate.page,
                            json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                        ),
                    )
                return self._load(connection, confirmation_id, review)

    def _load(
        self, connection: sqlite3.Connection, confirmation_id: str, current_review: RevenueReview
    ) -> RevenueConfirmation:
        """同一读快照恢复确认与两条事实，重新计算摘要检测缺行/损坏/来源变化。"""
        revision = current_review.revision
        header = connection.execute(
            "SELECT * FROM revenue_confirmations WHERE confirmation_id = ? "
            "AND workspace_id = ? AND document_id = ?",
            (confirmation_id, revision.workspace_id, revision.document_id),
        ).fetchone()
        if header is None:
            raise RevenueConfirmationError("confirmation_required")
        rows = connection.execute(
            "SELECT * FROM confirmed_revenue_facts WHERE confirmation_id = ? ORDER BY period",
            (confirmation_id,),
        ).fetchall()
        try:
            if len(rows) != 2:
                raise ValueError("确认事实不完整")
            stored_revision = RevenueSourceRevision(
                workspace_id=header["workspace_id"],
                document_id=header["document_id"],
                content_sha256=header["content_sha256"],
                attempt=header["attempt"],
                extraction_method=header["extraction_method"],
                extraction_version=header["extraction_version"],
            )
            candidates: list[RevenueCandidate] = []
            for row in rows:
                evidence = json.loads(row["evidence_json"])
                if not isinstance(evidence, list) or row["fact_key"] != "revenue":
                    raise ValueError("确认记录结构非法")
                value = Decimal(row["value_text"])
                if format(value, "f") != row["value_text"]:
                    raise ValueError("金额不是规范十进制文本")
                candidates.append(
                    RevenueCandidate(
                        workspace_id=stored_revision.workspace_id,
                        document_id=stored_revision.document_id,
                        source_ref=row["source_ref"],
                        chunk_id=row["chunk_id"],
                        source_file=row["source_file"],
                        page=row["page"],
                        period=row["period"],
                        value=value,
                        unit=FinancialUnit(row["unit"]),
                        evidence=tuple(RevenueEvidence(**item) for item in evidence),
                        extraction_method=stored_revision.extraction_method,
                        extraction_version=stored_revision.extraction_version,
                    )
                )
            stored_review = RevenueReview(stored_revision, tuple(candidates))
            confirmed_at = datetime.fromisoformat(header["confirmed_at"])
            kind = header["confirmation_kind"]
            if confirmed_at.tzinfo is None or kind not in ("local_operator", "simulated_test"):
                raise ValueError("确认动作元数据非法")
            if stored_review.snapshot_id != header["snapshot_id"]:
                raise ValueError("确认内容摘要不匹配")
        except (ValueError, TypeError, KeyError, ArithmeticError, RevenueConfirmationError) as exc:
            raise RevenueConfirmationError("confirmation_integrity_error") from exc
        if stored_review.snapshot_id != current_review.snapshot_id:
            raise RevenueConfirmationError("source_changed")
        return RevenueConfirmation(confirmation_id, confirmed_at, kind, stored_review)

    def load(self, *, confirmation_id: str, current_review: RevenueReview) -> RevenueConfirmation:
        """只有完整且匹配当前来源的确认可以读回；历史记录仍保留，不回退旧值。"""
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN")
                self._check_document(connection, current_review)
                return self._load(connection, confirmation_id, current_review)

    def fact_repository(
        self, *, confirmation_id: str, current_review: RevenueReview
    ) -> FinancialFactRepository:
        """为本次已查证计算创建范围受限的 SQLite 查询适配器，不注册进 runtime。"""
        return _CheckedSQLiteFinancialFacts(self, confirmation_id, current_review)


class _CheckedSQLiteFinancialFacts(FinancialFactRepository):
    """一次计算专用查询；每次查事实均整组读回，拒绝跨文档或跨指标引用。"""

    def __init__(
        self,
        repository: SQLiteRevenueConfirmationRepository,
        confirmation_id: str,
        current_review: RevenueReview,
    ) -> None:
        self._repository = repository
        self._confirmation_id = confirmation_id
        self._current_review = current_review

    def find_fact(
        self,
        *,
        execution_context: ToolExecutionContext,
        source_ref: str,
        fact_key: FinancialFactKey,
    ) -> FinancialFact | None:
        """从已保存确认读取金额；上下文必须匹配本次服务端核准的范围。"""
        revision = self._current_review.revision
        filters = execution_context.filters
        if (
            execution_context.trusted_context.workspace_id != revision.workspace_id
            or filters is None
            or filters.document_id != revision.document_id
            or fact_key is not FinancialFactKey.REVENUE
        ):
            return None
        confirmation = self._repository.load(
            confirmation_id=self._confirmation_id, current_review=self._current_review
        )
        for item in confirmation.confirmed_facts():
            if item.fact.source_ref == source_ref:
                return item.fact
        return None
