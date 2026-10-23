"""Streaming conversational agent for the Mahindra automotive assistant."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

from app.agent.system_prompt import SYSTEM_PROMPT
from app.config import get_settings
from app.sessions.store import SessionStore
from app.tools.handlers import DISPATCH as HANDLER_DISPATCH
from app.tools.definitions import TOOL_DEFINITIONS

TOOLS = TOOL_DEFINITIONS
STOP_SEQUENCES = ["\nUser:", "\nCustomer:"]


def _friendly_error(message: str) -> dict[str, str]:
    return {"type": "error", "message": message}


def _summarize_session(session: Any) -> str:
    """Create a short system summary of the in-flight session."""
    stage = getattr(session, "stage", "discovery")
    collected = getattr(session, "collected", {}) or {}
    if not collected:
        return f"Session context: stage={stage}; collected=none."

    parts = [f"{key}={value}" for key, value in collected.items() if value not in (None, "", [], {})]
    summary = ", ".join(parts) if parts else "no details captured yet"
    return f"Session context: stage={stage}; collected={summary}."


def _build_messages(session: Any) -> list[dict[str, Any]]:
    """Assemble a trimmed message list with the system prompt first."""
    system_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": _summarize_session(session)},
    ]
    history = list(getattr(session, "messages", []) or [])
    if len(history) > 20:
        history = history[-20:]
    return system_messages + history


async def _retry_tool_arguments(
    client: AsyncOpenAI,
    session: Any,
    tool_name: str,
    fallback_call_id: str,
) -> dict[str, Any]:
    """Retry a tool call once if the streamed argument JSON failed to decode."""
    messages = _build_messages(session)
    try:
        completion = await client.chat.completions.create(
            model=get_settings().groq_model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.2,
            stop=STOP_SEQUENCES,
            stream=False,
        )
        tool_calls = getattr(completion.choices[0].message, "tool_calls", None) or []
        if not tool_calls:
            return {}
        first_call = tool_calls[0]
        arguments = getattr(first_call.function, "arguments", "{}") or "{}"
        parsed = json.loads(arguments)
        if isinstance(parsed, dict):
            return parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return {"fallback": True, "tool_name": tool_name, "call_id": fallback_call_id}


async def run_agent(
    session_id: str | None,
    user_message: str,
    store: SessionStore | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream a chat turn and execute tool calls using the automotive assistant instructions."""
    store = store or SessionStore()
    llm_rounds = 0
    text_rounds = 0
    try:
        session = await store.get_or_create_session(session_id)
        await store.append_message(session.session_id, {"role": "user", "content": user_message})

        client = AsyncOpenAI(
            api_key=get_settings().groq_api_key,
            base_url="https://api.groq.com/openai/v1",
            timeout=20.0,
        )

        had_tool_round = False
        emitted_text_in_turn = False
        for _ in range(5):
            llm_rounds += 1
            messages = _build_messages(session)
            logger.warning("chat_llm_call session=%s message_count=%s tool_count=%s", session.session_id, len(messages), len(TOOLS))
            stream = await client.chat.completions.create(
                model=get_settings().groq_model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2,
                stop=STOP_SEQUENCES,
                stream=True,
            )

            tool_calls_by_index: dict[int, dict[str, Any]] = {}
            round_text = ""
            saw_tool_calls = False

            async for chunk in stream:
                choice = chunk.choices[0] if hasattr(chunk, "choices") and chunk.choices else None
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue

                if getattr(delta, "content", None):
                    round_text += delta.content

                tool_deltas = getattr(delta, "tool_calls", None) or []
                for tool_delta in tool_deltas:
                    saw_tool_calls = True
                    index = tool_delta.index
                    current = tool_calls_by_index.setdefault(
                        index,
                        {"id": tool_delta.id or "", "name": tool_delta.function.name or "", "arguments": ""},
                    )
                    if getattr(tool_delta, "id", None):
                        current["id"] = tool_delta.id
                    if getattr(tool_delta.function, "name", None):
                        current["name"] = tool_delta.function.name
                    if getattr(tool_delta.function, "arguments", None):
                        current["arguments"] += tool_delta.function.arguments

            logger.warning(
                "chat_llm_round_text session=%s round=%s saw_tools=%s text=%r",
                session.session_id,
                llm_rounds,
                saw_tool_calls,
                round_text,
            )

            if not saw_tool_calls:
                if round_text:
                    text_rounds += 1
                    if had_tool_round and emitted_text_in_turn:
                        yield {"type": "token", "text": "\n\n"}
                    await store.append_message(
                        session.session_id,
                        {"role": "assistant", "content": round_text},
                    )
                    yield {"type": "token", "text": round_text}
                    emitted_text_in_turn = True
                logger.warning("chat_llm_rounds session=%s rounds=%s", session.session_id, llm_rounds)
                logger.warning("chat_text_rounds session=%s text_rounds=%s", session.session_id, text_rounds)
                yield {"type": "done"}
                return

            had_tool_round = True

            assistant_tool_calls = [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": call["arguments"],
                    },
                }
                for call in sorted(tool_calls_by_index.values(), key=lambda item: item.get("id") or "")
            ]

            await store.append_message(
                session.session_id,
                {"role": "assistant", "content": None, "tool_calls": assistant_tool_calls},
            )

            for index, call in sorted(tool_calls_by_index.items()):
                tool_name = call.get("name") or "unknown_tool"
                call_id = call.get("id") or f"call_{index}"
                raw_arguments = call.get("arguments") or "{}"
                logger.warning(
                    "tool_call_start index=%s name=%s raw_arguments=%s",
                    index,
                    tool_name,
                    raw_arguments,
                )
                yield {"type": "tool_start", "tool": tool_name, "call_id": call_id}

                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    arguments = await _retry_tool_arguments(client, session, tool_name, call_id)
                    if not isinstance(arguments, dict):
                        arguments = {}

                if not isinstance(arguments, dict):
                    arguments = {}

                logger.warning("tool_call_parsed_args index=%s name=%s parsed_args=%s", index, tool_name, arguments)

                handler = HANDLER_DISPATCH.get(tool_name)
                if handler is None:
                    result = {"ok": False, "data": None, "error": "This action is not available right now."}
                else:
                    try:
                        result = await handler(**arguments)
                    except TypeError:
                        logger.exception("tool %s kwargs invocation failed with args %s", tool_name, arguments)
                        try:
                            result = await handler(arguments)
                        except (TypeError, ValueError, RuntimeError, OSError):
                            logger.exception("tool %s dict invocation failed with args %s", tool_name, arguments)
                            result = {"ok": False, "data": None, "error": "I couldn’t complete that request right now."}
                    except (TypeError, ValueError, RuntimeError, OSError):
                        logger.exception("tool %s invocation failed with args %s", tool_name, arguments)
                        result = {"ok": False, "data": None, "error": "I couldn’t complete that request right now."}
                    except Exception:
                        logger.exception("tool %s failed with args %s", tool_name, arguments)
                        result = {"ok": False, "data": None, "error": "I couldn’t complete that request right now."}

                logger.warning("tool_call_result index=%s name=%s result=%s", index, tool_name, result)

                if result.get("ok"):
                    session.stage = {
                        "get_vehicle_info": "discovery",
                        "create_lead": "discovery",
                        "lookup_deal": "pipeline",
                        "update_followup_preference": "pipeline",
                        "get_booking_status": "booking",
                        "create_service_ticket": "service",
                    }.get(tool_name, session.stage)
                    await store.set_stage(session.session_id, session.stage)
                    await store.update_collected(session.session_id, arguments)

                tool_result_message = {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": tool_name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
                await store.append_message(session.session_id, tool_result_message)
                yield {"type": "tool_end", "tool": tool_name, "ok": bool(result.get("ok", False)), "result": result}

            continue

        logger.warning("chat_llm_rounds session=%s rounds=%s", session.session_id, llm_rounds)
        logger.warning("chat_text_rounds session=%s text_rounds=%s", session.session_id, text_rounds)
        yield {"type": "done"}
    except Exception as exc:
        logger.warning("chat_llm_rounds session=%s rounds=%s", session_id, llm_rounds)
        logger.warning("chat_text_rounds session=%s text_rounds=%s", session_id, text_rounds)
        message = str(exc).lower()
        if "model" in message and ("not exist" in message or "access" in message or "not found" in message):
            yield _friendly_error(
                "The configured Groq model isn’t available for this account. Please switch to a model enabled in your Groq console."
            )
        else:
            yield _friendly_error("Sorry, I’m having a quick issue. Please try again in a moment.")
