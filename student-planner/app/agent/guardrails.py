class GuardrailViolation(Exception):
    """Raised when a guardrail is violated."""

    def __init__(self, message: str, suggestion: str):
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


def check_consecutive_ask_user(tool_history: list[str]) -> None:
    """Prevent LLM from calling ask_user twice in a row without doing actual work."""
    if len(tool_history) >= 2 and tool_history[-1] == "ask_user" and tool_history[-2] == "ask_user":
        raise GuardrailViolation(
            message="不能连续两次调用 ask_user，中间需要执行一步实际操作。",
            suggestion="请先执行一个工具操作，然后再询问用户。",
        )


def check_max_loop_iterations(iteration: int, max_iterations: int = 20) -> None:
    """Prevent infinite loops."""
    if iteration >= max_iterations:
        raise GuardrailViolation(
            message=f"Agent loop 已执行 {iteration} 步，超过最大限制 {max_iterations}。",
            suggestion="任务可能过于复杂，请拆分成更小的请求。",
        )


def check_unknown_tool(tool_name: str, known_tools: set[str]) -> None:
    """Prevent LLM from calling non-existent tools."""
    if tool_name not in known_tools:
        raise GuardrailViolation(
            message=f"工具 '{tool_name}' 不存在。",
            suggestion=f"可用的工具有：{', '.join(sorted(known_tools))}",
        )


def check_max_retries(tool_name: str, error_count: dict[str, int], max_retries: int = 2) -> None:
    """Prevent retrying the same failed tool too many times."""
    if error_count.get(tool_name, 0) >= max_retries:
        raise GuardrailViolation(
            message=f"工具 '{tool_name}' 已失败 {max_retries} 次。",
            suggestion="请告诉用户出了问题，不要继续重试。",
        )