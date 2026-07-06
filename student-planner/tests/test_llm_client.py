from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.llm_client import chat_completion, create_llm_client
from app.config import settings


def test_create_llm_client_uses_primary_llm_settings(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "primary-key")
    monkeypatch.setattr(settings, "llm_base_url", "https://primary.example/v1")
    monkeypatch.setattr(settings, "llm_model", "primary-model")

    client = create_llm_client()

    assert str(client.base_url) == f"{settings.llm_base_url}/"
    assert client.api_key == settings.llm_api_key


def test_create_llm_client_falls_back_to_rag_embedding_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "sk-placeholder")
    monkeypatch.setattr(settings, "llm_base_url", "https://primary.example/v1")
    monkeypatch.setattr(settings, "llm_model", "primary-model")
    monkeypatch.setattr(settings, "rag_embedding_api_key", "dashscope-key")
    monkeypatch.setattr(settings, "rag_embedding_base_url", "https://dashscope.example/compatible-mode/v1")

    client = create_llm_client()

    assert str(client.base_url) == "https://dashscope.example/compatible-mode/v1/"
    assert client.api_key == "dashscope-key"


@pytest.mark.asyncio
async def test_chat_completion_text_response(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "primary-key")
    monkeypatch.setattr(settings, "llm_model", "primary-model")
    mock_message = MagicMock()
    mock_message.content = "你好！有什么可以帮你的？"
    mock_message.tool_calls = None

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await chat_completion(mock_client, [{"role": "user", "content": "你好"}])

    assert result["role"] == "assistant"
    assert result["content"] == "你好！有什么可以帮你的？"
    assert "tool_calls" not in result
    assert mock_client.chat.completions.create.await_args.kwargs["model"] == "primary-model"


@pytest.mark.asyncio
async def test_chat_completion_uses_rag_embedding_key_fallback_model(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "sk-placeholder")
    monkeypatch.setattr(settings, "llm_model", "primary-model")
    monkeypatch.setattr(settings, "rag_embedding_api_key", "dashscope-key")

    mock_message = MagicMock()
    mock_message.content = "改革开放是 1978 年开始的。"
    mock_message.tool_calls = None

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await chat_completion(mock_client, [{"role": "user", "content": "改革开放是什么时候的事情"}])

    assert result["content"] == "改革开放是 1978 年开始的。"
    assert mock_client.chat.completions.create.await_args.kwargs["model"] == "qwen-plus"


@pytest.mark.asyncio
async def test_chat_completion_tool_call():
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function.name = "list_courses"
    mock_tool_call.function.arguments = "{}"

    mock_message = MagicMock()
    mock_message.content = None
    mock_message.tool_calls = [mock_tool_call]

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await chat_completion(
        mock_client,
        [{"role": "user", "content": "我有什么课"}],
        tools=[{"type": "function", "function": {"name": "list_courses"}}],
    )

    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["function"]["name"] == "list_courses"
