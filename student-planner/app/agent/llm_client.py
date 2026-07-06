from typing import Any, AsyncGenerator

from openai import AsyncOpenAI

from app.config import settings

_RAG_ANSWER_FALLBACK_MODEL = "qwen-plus"


def _has_real_key(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and stripped not in {"sk-placeholder", "placeholder", "changeme"}


def _runtime_llm_config() -> tuple[str, str, str]:
    if _has_real_key(settings.llm_api_key):
        return settings.llm_api_key, settings.llm_base_url, settings.llm_model
    if _has_real_key(settings.rag_embedding_api_key):
        return settings.rag_embedding_api_key, settings.rag_embedding_base_url, _RAG_ANSWER_FALLBACK_MODEL
    return settings.llm_api_key, settings.llm_base_url, settings.llm_model


def create_llm_client() -> AsyncOpenAI:
    """Create an OpenAI-compatible async client for provider-switched backends."""
    api_key, base_url, _ = _runtime_llm_config()
    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
    )


async def chat_completion(
    client: AsyncOpenAI,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str = "auto",
) -> dict[str, Any]:
    """Call the LLM and normalize the response into a serializable dict."""
    _, _, model = _runtime_llm_config()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": settings.llm_max_tokens,
        "temperature": settings.llm_temperature,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    response = await client.chat.completions.create(**kwargs)
    message = response.choices[0].message

    result: dict[str, Any] = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        result["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
            for tool_call in message.tool_calls
        ]

    return result


async def chat_completion_stream(
    client: AsyncOpenAI,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str = "auto",
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream chat completion chunks and emit a normalized final response."""
    _, _, model = _runtime_llm_config()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": settings.llm_max_tokens,
        "temperature": settings.llm_temperature,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice

    stream = await client.chat.completions.create(**kwargs)

    content_parts: list[str] = []
    tool_calls_by_index: dict[int, dict[str, Any]] = {}

    async for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue

        choice = choices[0]
        delta = getattr(choice, "delta", None)
        if delta is None:
            continue

        content_delta = getattr(delta, "content", None)
        if content_delta:
            content_parts.append(content_delta)
            yield {"type": "content_delta", "delta": content_delta}

        for tool_call_delta in getattr(delta, "tool_calls", None) or []:
            index = getattr(tool_call_delta, "index", None)
            if index is None:
                index = len(tool_calls_by_index)

            tool_call = tool_calls_by_index.setdefault(
                index,
                {
                    "id": f"call_{index}",
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                },
            )

            tool_call_id = getattr(tool_call_delta, "id", None)
            if tool_call_id:
                tool_call["id"] = tool_call_id

            function_delta = getattr(tool_call_delta, "function", None)
            if function_delta is None:
                continue

            function_name = getattr(function_delta, "name", None)
            if function_name:
                tool_call["function"]["name"] += function_name

            function_arguments = getattr(function_delta, "arguments", None)
            if function_arguments:
                tool_call["function"]["arguments"] += function_arguments

    response: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(content_parts) or None,
    }
    if tool_calls_by_index:
        response["tool_calls"] = [tool_calls_by_index[index] for index in sorted(tool_calls_by_index)]

    yield {"type": "response", "response": response}
