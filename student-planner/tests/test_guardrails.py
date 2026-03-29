import pytest

from app.agent.guardrails import (
    GuardrailViolation,
    check_consecutive_ask_user,
    check_max_loop_iterations,
    check_max_retries,
    check_unknown_tool,
)


def test_consecutive_ask_user_violation():
    with pytest.raises(GuardrailViolation):
        check_consecutive_ask_user(["ask_user", "ask_user"])


def test_consecutive_ask_user_ok():
    check_consecutive_ask_user(["list_courses", "ask_user"])
    check_consecutive_ask_user(["ask_user", "list_courses"])


def test_max_iterations():
    with pytest.raises(GuardrailViolation):
        check_max_loop_iterations(20, max_iterations=20)
    check_max_loop_iterations(19, max_iterations=20)


def test_unknown_tool():
    with pytest.raises(GuardrailViolation):
        check_unknown_tool("hack_system", {"list_courses", "ask_user"})
    check_unknown_tool("list_courses", {"list_courses", "ask_user"})


def test_max_retries():
    errors = {"list_courses": 2}
    with pytest.raises(GuardrailViolation):
        check_max_retries("list_courses", errors, max_retries=2)
    check_max_retries("list_courses", {"list_courses": 1}, max_retries=2)