"""Multistage AI agent orchestrating tool calls with Groq/OpenAI-compatible API."""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings
from app.sessions.store import SessionStore
from app.tools.zoho_tools import (
    CreateServiceCaseInput,
    DealerProfileInput,
    SearchLeadsInput,
    create_service_case,
    fetch_dealer_profile,
    search_leads,
)


class ChatAgent:
    """Coordinate chat flow, tool execution, and Zoho CRM lookups."""

    def __init__(self, session_store: SessionStore | None = None, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self.session_store = session_store or SessionStore()
        self.tools: dict[str, Any] = {
            "search_leads": search_leads,
            "fetch_dealer_profile": fetch_dealer_profile,
            "create_service_case": create_service_case,
        }
        self.tool_schemas = [
            {
                "type": "function",
                "function": {
                    "name": "search_leads",
                    "description": "Search Zoho CRM leads based on customer or dealer filters.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_name": {"type": "string"},
                            "phone": {"type": "string"},
                            "email": {"type": "string"},
                            "city": {"type": "string"},
                            "dealer_id": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_dealer_profile",
                    "description": "Fetch dealership profile information from Zoho CRM.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "dealer_id": {"type": "string"},
                            "dealer_name": {"type": "string"},
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_service_case",
                    "description": "Create a service request or complaint case for a customer.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "subject": {"type": "string"},
                            "description": {"type": "string"},
                            "customer_name": {"type": "string"},
                            "phone": {"type": "string"},
                            "email": {"type": "string"},
                            "priority": {"type": "string"},
                            "dealer_id": {"type": "string"},
                        },
                        "required": ["subject", "description", "customer_name"],
                    },
                },
            },
        ]

        self.openai_client = (
            AsyncOpenAI(api_key=self.settings.openai_api_key, base_url=self.settings.openai_base_url)
            if self.settings.openai_api_key
            else None
        )

    async def _invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute the requested tool and convert any exception into a safe payload."""
        tool_callable = self.tools.get(tool_name)
        if tool_callable is None:
            return {"ok": False, "data": None, "error": f"Unknown tool: {tool_name}"}

        try:
            return await tool_callable(arguments)
        except Exception as exc:  # pragma: no cover - defensive guard
            return {"ok": False, "data": None, "error": str(exc)}

    async def respond(self, user_message: str, session_id: str | None = None) -> dict[str, Any]:
        """Handle one chat turn and optionally invoke CRM tools via the model."""
        session_id, history = self.session_store.get_or_create(session_id)
        self.session_store.add_message(session_id, "user", user_message)

        if self.openai_client is None:
            response_text = (
                "I’m ready to help with vehicle sales, service, and dealer workflows. "
                "Add your Groq API key in the backend environment to enable live AI responses."
            )
            self.session_store.add_message(session_id, "assistant", response_text)
            return {"session_id": session_id, "reply": response_text, "tool_results": []}

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a multistage AI agent for a Mahindra-style automotive OEM. "
                    "You can search leads, fetch dealer profiles, and create service cases in Zoho CRM. "
                    "Keep responses concise and action-oriented."
                ),
            }
        ]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        completion = await self.openai_client.chat.completions.create(
            model=self.settings.openai_model,
            messages=messages,
            tools=self.tool_schemas,
            tool_choice="auto",
        )

        assistant_message = completion.choices[0].message
        tool_results: list[dict[str, Any]] = []
        reply = assistant_message.content or "I’m checking the relevant CRM data now."

        if assistant_message.tool_calls:
            for tool_call in assistant_message.tool_calls:
                arguments = json.loads(tool_call.function.arguments or "{}")
                tool_result = await self._invoke_tool(tool_call.function.name, arguments)
                tool_results.append({tool_call.function.name: tool_result})
                reply = (
                    f"I checked the CRM data for {tool_call.function.name} and here is the result: "
                    f"{json.dumps(tool_result, ensure_ascii=False)}"
                )

        self.session_store.add_message(session_id, "assistant", reply)
        return {"session_id": session_id, "reply": reply, "tool_results": tool_results}
