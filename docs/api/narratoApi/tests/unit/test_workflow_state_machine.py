from __future__ import annotations

import pytest

from narrato_api.workflows.state_machine import (
    StateTransitionError,
    is_automatic_retry_candidate,
    transition_workflow_state,
)


def test_user_cannot_cancel_or_manually_retry_a_workflow() -> None:
    with pytest.raises(StateTransitionError, match="cancel"):
        transition_workflow_state("running", "cancelled", actor="user")

    with pytest.raises(StateTransitionError, match="retry"):
        transition_workflow_state("failed", "running", actor="user")


def test_waiting_for_edit_has_no_automatic_timeout_or_failure_transition() -> None:
    assert (
        transition_workflow_state("waiting_for_edit", "failed", actor="system") is False
    )
    assert (
        transition_workflow_state(
            "waiting_for_edit", "waiting_for_edit", actor="system"
        )
        is True
    )


def test_terminal_workflow_states_cannot_be_recovered() -> None:
    for terminal_state in ("completed", "failed"):
        assert (
            transition_workflow_state(terminal_state, "running", actor="system")
            is False
        )


def test_only_retryable_failed_attempt_with_remaining_budget_is_a_retry_candidate() -> (
    None
):
    assert is_automatic_retry_candidate(
        node_state="failed", retryable=True, attempt_count=1, max_attempts=3
    )
    assert not is_automatic_retry_candidate(
        node_state="failed", retryable=False, attempt_count=1, max_attempts=3
    )
    assert not is_automatic_retry_candidate(
        node_state="failed", retryable=True, attempt_count=3, max_attempts=3
    )
    assert not is_automatic_retry_candidate(
        node_state="succeeded", retryable=True, attempt_count=1, max_attempts=3
    )
