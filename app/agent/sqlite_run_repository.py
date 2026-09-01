from contextlib import closing
from datetime import UTC, datetime
import json
from uuid import uuid4
from pathlib import Path
import sqlite3

from app.agent.run_models import (
    AgentRun,
    AgentRunNotFoundError,
    AgentRunStateConflictError,
    AgentTerminalStatus,
    RunEvent,
    RunEventSequenceError,
    RunEventType,
    RunStatus,
)


class SQLiteAgentRunRepository:
    """使用独立 SQLite 表持久化 Agent Run 和安全事件。"""

    def __init__(self, database_path: Path) -> None:
        """绑定数据库路径并幂等初始化 Run/Event 表。"""
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._database_path = database_path
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        """创建启用外键约束的新 SQLite 连接。"""
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row

        # SQLite 的外键开关属于单个连接，不能只在初始化时设置一次
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize_schema(self) -> None:
        """幂等创建 Agent Run 和 Event 表。

        表级约束保护状态组合、事件外键和复合唯一性；
        连续 sequence、workspace 隔离和原子终结由 repository 写方法负责。
        """
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_runs (
                        run_id TEXT PRIMARY KEY,
                        workspace_id TEXT NOT NULL,
                        status TEXT NOT NULL
                            CHECK (
                                status IN (
                                    'running',
                                    'succeeded',
                                    'failed'
                                )
                            ),
                        terminal_status TEXT
                            CHECK (
                                terminal_status IS NULL
                                OR terminal_status IN (
                                    'success',
                                    'protocol_error',
                                    'tool_error',
                                    'provider_error',
                                    'max_steps_reached'
                                )
                            ),
                        started_at TEXT NOT NULL,
                        ended_at TEXT,
                        safe_result_json TEXT,
                        execution_config_version TEXT NOT NULL,
                        CHECK (
                            (
                                status = 'running'
                                AND terminal_status IS NULL
                                AND ended_at IS NULL
                                AND safe_result_json IS NULL
                            )
                            OR
                            (
                                status = 'succeeded'
                                AND terminal_status = 'success'
                                AND ended_at IS NOT NULL
                            )
                            OR
                            (
                                status = 'failed'
                                AND terminal_status IN (
                                    'protocol_error',
                                    'tool_error',
                                    'provider_error',
                                    'max_steps_reached'
                                )
                                AND ended_at IS NOT NULL
                            )
                        )
                    )
                    """
                )

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS run_events (
                        run_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL
                            CHECK (sequence > 0),
                        event_type TEXT NOT NULL
                            CHECK (
                                event_type IN (
                                    'tool_requested',
                                    'tool_succeeded',
                                    'tool_failed',
                                    'run_succeeded',
                                    'run_failed'
                                )
                            ),
                        payload_json TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        PRIMARY KEY (run_id, sequence),
                        FOREIGN KEY (run_id)
                            REFERENCES agent_runs(run_id)
                    )
                    """
                )

    def start_run(self, *, workspace_id: str, execution_config_version: str) -> AgentRun:
        """创建并持久化一条由服务端生成身份的运行中 Agent Run。"""
        run_id = str(uuid4())
        status = RunStatus.RUNNING
        terminal_status = None
        started_at = datetime.now(UTC)
        ended_at = None
        safe_result = None

        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO agent_runs (run_id, workspace_id, status, terminal_status, started_at, ended_at, safe_result_json, execution_config_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        workspace_id,
                        status.value,
                        terminal_status,
                        started_at.isoformat(),
                        ended_at,
                        safe_result,
                        execution_config_version,
                    ),
                )
                return AgentRun(
                    run_id=run_id,
                    workspace_id=workspace_id,
                    status=status,
                    terminal_status=terminal_status,
                    started_at=started_at,
                    ended_at=ended_at,
                    safe_result=safe_result,
                    execution_config_version=execution_config_version,
                )

    def _row_to_run(self, row: sqlite3.Row) -> AgentRun:
        """把 SQLite 行恢复为 AgentRun 领域对象。"""
        return AgentRun(
            run_id=row["run_id"],
            workspace_id=row["workspace_id"],
            status=RunStatus(row["status"]),
            terminal_status=AgentTerminalStatus(row["terminal_status"])
            if row["terminal_status"]
            else None,
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
            safe_result=(
                None
                if row["safe_result_json"] is None
                else json.loads(str(row["safe_result_json"]))
            ),
            execution_config_version=row["execution_config_version"],
        )

    def get_run(self, *, workspace_id: str, run_id: str) -> AgentRun | None:
        """按可信 workspace 和 run_id 查询一次 Agent Run。"""
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    """
                    SELECT * FROM agent_runs WHERE workspace_id = ? AND run_id = ?
                    """,
                    (workspace_id, run_id),
                ).fetchone()
                if row is None:
                    return None
                return self._row_to_run(row)

    def append_event(self, *, workspace_id: str, event: RunEvent) -> RunEvent:
        """向运行中的 Run 追加一条连续的非终态安全事件。"""
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")

                run_row = connection.execute(
                    """
                    SELECT status
                    FROM agent_runs
                    WHERE workspace_id = ? AND run_id = ?
                    """,
                    (workspace_id, event.run_id),
                ).fetchone()

                if run_row is None:
                    raise AgentRunNotFoundError(f"Run {event.run_id} 不存在")

                if RunStatus(str(run_row["status"])) is not RunStatus.RUNNING:
                    raise AgentRunStateConflictError(f"Run {event.run_id} 不是运行中状态")

                if event.event_type in {
                    RunEventType.RUN_SUCCEEDED,
                    RunEventType.RUN_FAILED,
                }:
                    raise AgentRunStateConflictError("终态事件只能由 finalize_run 写入")

                sequence_row = connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0)
                    FROM run_events
                    WHERE run_id = ?
                    """,
                    (event.run_id,),
                ).fetchone()

                if sequence_row is None:
                    raise RuntimeError("读取 Event sequence 失败")

                expected_sequence = int(sequence_row[0]) + 1
                if event.sequence != expected_sequence:
                    raise RunEventSequenceError(f"下一条 Event sequence 必须是 {expected_sequence}")

                connection.execute(
                    """
                    INSERT INTO run_events (
                        run_id,
                        sequence,
                        event_type,
                        payload_json,
                        occurred_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        event.run_id,
                        event.sequence,
                        event.event_type.value,
                        json.dumps(event.payload, ensure_ascii=False),
                        event.occurred_at.isoformat(),
                    ),
                )

        return event

    def _row_to_event(self, row: sqlite3.Row) -> RunEvent:
        """把 SQLite 行恢复为 RunEvent 领域对象。"""
        return RunEvent(
            run_id=row["run_id"],
            sequence=row["sequence"],
            event_type=RunEventType(row["event_type"]),
            payload=json.loads(str(row["payload_json"])),
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
        )

    def list_events(self, *, workspace_id: str, run_id: str) -> list[RunEvent]:
        """按可信 workspace 查询一次 Run 的全部有序事件。"""
        with closing(self._connect()) as connection:
            with connection:
                run_row = connection.execute(
                    """
                    SELECT 1
                    FROM agent_runs
                    WHERE workspace_id = ? AND run_id = ?
                    """,
                    (workspace_id, run_id),
                ).fetchone()
                if run_row is None:
                    raise AgentRunNotFoundError("Agent Run 不存在")
                rows = connection.execute(
                    """
                    SELECT * FROM run_events
                    WHERE run_id=?
                    ORDER BY sequence ASC
                    """,
                    (run_id,),
                ).fetchall()
                return [self._row_to_event(row) for row in rows]

    def finalize_run(
        self,
        *,
        workspace_id: str,
        terminal_status: AgentTerminalStatus,
        safe_result: dict[str, object] | None,
        terminal_event: RunEvent,
    ) -> AgentRun:
        """在同一事务中写入终态 Event 并终结 Agent Run。"""
        if not isinstance(terminal_status, AgentTerminalStatus):
            raise TypeError("terminal_status 必须是 AgentTerminalStatus")

        if safe_result is not None and not isinstance(safe_result, dict):
            raise TypeError("safe_result 必须是字典或 None")

        safe_result_json = (
            None if safe_result is None else json.dumps(safe_result, ensure_ascii=False)
        )

        if terminal_status is AgentTerminalStatus.SUCCESS:
            run_status = RunStatus.SUCCEEDED
            expected_event_type = RunEventType.RUN_SUCCEEDED
        else:
            run_status = RunStatus.FAILED
            expected_event_type = RunEventType.RUN_FAILED

        if terminal_event.event_type is not expected_event_type:
            raise AgentRunStateConflictError(f"终态 Event 必须是 {expected_event_type.value}")

        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")

                run_row = connection.execute(
                    """
                    SELECT *
                    FROM agent_runs
                    WHERE workspace_id = ? AND run_id = ?
                    """,
                    (workspace_id, terminal_event.run_id),
                ).fetchone()

                if run_row is None:
                    raise AgentRunNotFoundError("Agent Run 不存在")

                if RunStatus(str(run_row["status"])) is not RunStatus.RUNNING:
                    raise AgentRunStateConflictError("Agent Run 已经终结")

                sequence_row = connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0)
                    FROM run_events
                    WHERE run_id = ?
                    """,
                    (terminal_event.run_id,),
                ).fetchone()

                if sequence_row is None:
                    raise RuntimeError("读取 Event sequence 失败")

                expected_sequence = int(sequence_row[0]) + 1
                if terminal_event.sequence != expected_sequence:
                    raise RunEventSequenceError(f"终态 Event sequence 必须是 {expected_sequence}")

                final_run = AgentRun(
                    run_id=str(run_row["run_id"]),
                    workspace_id=str(run_row["workspace_id"]),
                    status=run_status,
                    terminal_status=terminal_status,
                    started_at=datetime.fromisoformat(str(run_row["started_at"])),
                    ended_at=terminal_event.occurred_at,
                    safe_result=safe_result,
                    execution_config_version=str(run_row["execution_config_version"]),
                )

                # 终态 Event 与下面的 Run 更新共享当前事务。
                connection.execute(
                    """
                    INSERT INTO run_events (
                        run_id,
                        sequence,
                        event_type,
                        payload_json,
                        occurred_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        terminal_event.run_id,
                        terminal_event.sequence,
                        terminal_event.event_type.value,
                        json.dumps(terminal_event.payload, ensure_ascii=False),
                        terminal_event.occurred_at.isoformat(),
                    ),
                )

                update_cursor = connection.execute(
                    """
                    UPDATE agent_runs
                    SET
                        status = ?,
                        terminal_status = ?,
                        ended_at = ?,
                        safe_result_json = ?
                    WHERE workspace_id = ?
                        AND run_id = ?
                        AND status = 'running'
                    """,
                    (
                        final_run.status.value,
                        terminal_status.value,
                        final_run.ended_at.isoformat() if final_run.ended_at else None,
                        safe_result_json,
                        workspace_id,
                        final_run.run_id,
                    ),
                )

                if update_cursor.rowcount != 1:
                    raise AgentRunStateConflictError("Agent Run 无法原子终结")

        return final_run
