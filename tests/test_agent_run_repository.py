import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

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
from app.agent.sqlite_run_repository import SQLiteAgentRunRepository


def _event(
    run: AgentRun,
    *,
    sequence: int,
    event_type: RunEventType = RunEventType.TOOL_REQUESTED,
) -> RunEvent:
    """构造带安全白名单 payload 的测试事件。"""
    return RunEvent(
        run_id=run.run_id,
        sequence=sequence,
        event_type=event_type,
        payload={"tool_name": "search_finance_docs", "tool_call_id": f"call-{sequence}"},
        occurred_at=run.started_at + timedelta(seconds=sequence),
    )


def _terminal_event(
    run: AgentRun,
    *,
    sequence: int,
    terminal_status: AgentTerminalStatus,
) -> RunEvent:
    """构造与精确终态一致的测试终态事件。"""
    succeeded = terminal_status is AgentTerminalStatus.SUCCESS
    return RunEvent(
        run_id=run.run_id,
        sequence=sequence,
        event_type=(RunEventType.RUN_SUCCEEDED if succeeded else RunEventType.RUN_FAILED),
        payload={"terminal_status": terminal_status.value},
        occurred_at=run.started_at + timedelta(seconds=sequence),
    )


def test_repository_reopen_preserves_run_and_ordered_events(tmp_path: Path) -> None:
    """验证 repository 重开后 Run 与有序事件仍可查询。"""
    database_path = tmp_path / "agent-runs.db"
    repository = SQLiteAgentRunRepository(database_path)
    started = repository.start_run(
        workspace_id="WS-A",
        execution_config_version="agent-run-v1",
    )
    repository.append_event(
        workspace_id="WS-A",
        event=_event(started, sequence=1),
    )
    finalized = repository.finalize_run(
        workspace_id="WS-A",
        terminal_status=AgentTerminalStatus.SUCCESS,
        safe_result={"final_answer_available": True},
        terminal_event=_terminal_event(
            started,
            sequence=2,
            terminal_status=AgentTerminalStatus.SUCCESS,
        ),
    )

    reopened = SQLiteAgentRunRepository(database_path)

    assert reopened.get_run(workspace_id="WS-A", run_id=started.run_id) == finalized
    events = reopened.list_events(workspace_id="WS-A", run_id=started.run_id)
    assert [event.sequence for event in events] == [1, 2]
    assert [event.event_type for event in events] == [
        RunEventType.TOOL_REQUESTED,
        RunEventType.RUN_SUCCEEDED,
    ]


def test_repository_rejects_non_contiguous_and_duplicate_sequences(
    tmp_path: Path,
) -> None:
    """验证 sequence 必须从 1 开始严格连续，且复合主键拒绝重复。"""
    database_path = tmp_path / "agent-runs.db"
    repository = SQLiteAgentRunRepository(database_path)
    started = repository.start_run(
        workspace_id="WS-A",
        execution_config_version="agent-run-v1",
    )

    with pytest.raises(RunEventSequenceError):
        repository.append_event(
            workspace_id="WS-A",
            event=_event(started, sequence=2),
        )

    first_event = _event(started, sequence=1)
    repository.append_event(workspace_id="WS-A", event=first_event)
    with pytest.raises(RunEventSequenceError):
        repository.append_event(workspace_id="WS-A", event=first_event)
    with pytest.raises(RunEventSequenceError):
        repository.append_event(
            workspace_id="WS-A",
            event=_event(started, sequence=3),
        )

    with sqlite3.connect(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO run_events (
                    run_id, sequence, event_type, payload_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    first_event.run_id,
                    first_event.sequence,
                    first_event.event_type.value,
                    "{}",
                    first_event.occurred_at.isoformat(),
                ),
            )

    assert [
        event.sequence
        for event in repository.list_events(
            workspace_id="WS-A",
            run_id=started.run_id,
        )
    ] == [1]


def test_repository_hides_run_existence_across_workspaces(tmp_path: Path) -> None:
    """验证错误 workspace 与不存在 Run 共用 not-found 语义。"""
    repository = SQLiteAgentRunRepository(tmp_path / "agent-runs.db")
    started = repository.start_run(
        workspace_id="WS-A",
        execution_config_version="agent-run-v1",
    )

    assert repository.get_run(workspace_id="WS-B", run_id=started.run_id) is None
    assert repository.get_run(workspace_id="WS-B", run_id="missing-run") is None

    for run_id in (started.run_id, "missing-run"):
        with pytest.raises(AgentRunNotFoundError, match="Agent Run 不存在"):
            repository.list_events(workspace_id="WS-B", run_id=run_id)


def test_repository_rejects_terminal_append_and_post_terminal_changes(
    tmp_path: Path,
) -> None:
    """验证终态只能原子写入一次，终态后不得再追加。"""
    repository = SQLiteAgentRunRepository(tmp_path / "agent-runs.db")
    started = repository.start_run(
        workspace_id="WS-A",
        execution_config_version="agent-run-v1",
    )
    terminal_event = _terminal_event(
        started,
        sequence=1,
        terminal_status=AgentTerminalStatus.SUCCESS,
    )

    with pytest.raises(AgentRunStateConflictError, match="finalize_run"):
        repository.append_event(workspace_id="WS-A", event=terminal_event)

    repository.finalize_run(
        workspace_id="WS-A",
        terminal_status=AgentTerminalStatus.SUCCESS,
        safe_result={"final_answer_available": True},
        terminal_event=terminal_event,
    )

    with pytest.raises(AgentRunStateConflictError, match="已经终结"):
        repository.finalize_run(
            workspace_id="WS-A",
            terminal_status=AgentTerminalStatus.SUCCESS,
            safe_result={"final_answer_available": True},
            terminal_event=terminal_event,
        )
    with pytest.raises(AgentRunStateConflictError, match="不是运行中"):
        repository.append_event(
            workspace_id="WS-A",
            event=_event(started, sequence=2),
        )


def test_finalize_rolls_back_terminal_event_when_run_update_fails(tmp_path: Path) -> None:
    """验证 Run 更新失败时，同事务的终态事件也回滚。"""
    database_path = tmp_path / "agent-runs.db"
    repository = SQLiteAgentRunRepository(database_path)
    started = repository.start_run(
        workspace_id="WS-A",
        execution_config_version="agent-run-v1",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_agent_run_update
            BEFORE UPDATE ON agent_runs
            BEGIN
                SELECT RAISE(ABORT, 'forced update failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="forced update failure"):
        repository.finalize_run(
            workspace_id="WS-A",
            terminal_status=AgentTerminalStatus.SUCCESS,
            safe_result={"final_answer_available": True},
            terminal_event=_terminal_event(
                started,
                sequence=1,
                terminal_status=AgentTerminalStatus.SUCCESS,
            ),
        )

    reopened = SQLiteAgentRunRepository(database_path)
    persisted = reopened.get_run(workspace_id="WS-A", run_id=started.run_id)
    assert persisted is not None
    assert persisted.status is RunStatus.RUNNING
    assert persisted.terminal_status is None
    assert reopened.list_events(workspace_id="WS-A", run_id=started.run_id) == []
