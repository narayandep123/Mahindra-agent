"""Regression tests for CRM tool-safe responses."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent.agent import run_agent
from app.sessions.store import SessionStore
from app.tools.handlers import create_lead, lookup_deal
from app.tools.zoho_tools import create_service_case, fetch_dealer_profile, search_leads


@pytest.mark.asyncio
async def test_search_leads_returns_safe_tool_response() -> None:
    """Search tool must never raise to the caller when credentials are absent."""
    result = await search_leads({"customer_name": "Aman", "limit": 2})
    assert isinstance(result, dict)
    assert "ok" in result
    assert "data" in result
    assert "error" in result


@pytest.mark.asyncio
async def test_fetch_dealer_profile_returns_safe_tool_response() -> None:
    """Dealer lookup should also return a structured failure payload."""
    result = await fetch_dealer_profile({"dealer_name": "Mahindra City"})
    assert isinstance(result, dict)
    assert "ok" in result
    assert "data" in result
    assert "error" in result


@pytest.mark.asyncio
async def test_create_case_returns_safe_tool_response() -> None:
    """Service case creation must fail gracefully without Zoho credentials."""
    result = await create_service_case(
        {
            "subject": "Vehicle service request",
            "description": "Tire pressure warning",
            "customer_name": "Shreya",
            "phone": "9876543210",
        }
    )
    assert isinstance(result, dict)
    assert "ok" in result
    assert "data" in result
    assert "error" in result


@pytest.mark.asyncio
async def test_create_lead_missing_required_fields_reports_cleanly() -> None:
    """Empty required field values should be surfaced directly as missing-field errors."""
    result = await create_lead(
        full_name="Aman Gupta",
        phone="9876543210",
        email="",
        city="Delhi",
        vehicle_model="Scorpio",
    )
    assert result["ok"] is False
    assert result["data"] == {"missing_fields": ["email"]}
    assert result["error"] == "Please provide the missing required fields."


@pytest.mark.asyncio
async def test_duplicate_lead_returns_existing_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """If a lead already exists, the tool should return the existing lead without creating another."""

    async def fake_find_lead_by_phone(phone: str, client=None):
        return {"id": "L-42", "Phone": phone}

    monkeypatch.setattr("app.tools.handlers.find_lead_by_phone", fake_find_lead_by_phone)

    result = await create_lead(
        full_name="Aman Gupta",
        phone="9876543210",
        email="aman@example.com",
        city="Delhi",
        vehicle_model="Scorpio",
    )

    assert result["ok"] is True
    assert result["data"]["lead_id"] == "L-42"
    assert result["error"] == "A lead already exists for this customer."


@pytest.mark.asyncio
async def test_lookup_deal_missing_record_returns_structured_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deal lookups should return a clean failure payload when no match exists."""

    async def fake_search_deals(*args, **kwargs):
        return []

    async def fake_find_lead_by_phone(*args, **kwargs):
        return None

    monkeypatch.setattr("app.tools.handlers.search_deals", fake_search_deals)
    monkeypatch.setattr("app.tools.handlers.find_lead_by_phone", fake_find_lead_by_phone)

    result = await lookup_deal(phone="9876543210")

    assert result["ok"] is False
    assert result["error"] == "No matching deal was found."


@pytest.mark.asyncio
async def test_lookup_deal_falls_back_to_lead_when_deal_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """If no deal matches, lookup should return lead-based confirmation when a lead exists."""

    async def fake_search_deals(*args, **kwargs):
        return []

    async def fake_find_lead_by_phone(phone: str, client=None):
        return {"id": "L-77", "Vehicle_Model": "XUV700"}

    monkeypatch.setattr("app.tools.handlers.search_deals", fake_search_deals)
    monkeypatch.setattr("app.tools.handlers.find_lead_by_phone", fake_find_lead_by_phone)

    result = await lookup_deal(phone="9876543210")

    assert result["ok"] is True
    assert result["data"]["found_as"] == "lead"
    assert result["data"]["vehicle_model"] == "XUV700"
    assert "confirm the schedule shortly" in result["data"]["message"]


@pytest.mark.asyncio
async def test_run_agent_handles_tool_call_then_final_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """The streaming agent should execute a tool call and continue to a final assistant answer."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    class FakeFunction:
        def __init__(self, name: str, arguments: str):
            self.name = name
            self.arguments = arguments

    class FakeToolCallDelta:
        def __init__(self, index: int, function: FakeFunction, call_id: str):
            self.index = index
            self.id = call_id
            self.function = function

    class FakeDelta:
        def __init__(self, *, content: str | None = None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls or []

    class FakeChoice:
        def __init__(self, delta: FakeDelta):
            self.delta = delta

    class FakeChatChunk:
        def __init__(self, delta: FakeDelta):
            self.choices = [FakeChoice(delta)]

    class FakeStream:
        def __init__(self, payloads):
            self.payloads = payloads
            self._index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self.payloads):
                raise StopAsyncIteration
            payload = self.payloads[self._index]
            self._index += 1
            return payload

    class FakeCompletions:
        def __init__(self):
            self.calls = 0

        async def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return FakeStream(
                    [
                        FakeChatChunk(
                            FakeDelta(
                                tool_calls=[
                                    FakeToolCallDelta(
                                        0,
                                        FakeFunction("lookup_deal", '{"phone":"9876543210"}'),
                                        "call_1",
                                    )
                                ]
                            )
                        )
                    ]
                )
            return FakeStream(
                [
                    FakeChatChunk(FakeDelta(content="I found the relevant update for you.")),
                ]
            )

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("app.agent.agent.AsyncOpenAI", lambda **kwargs: FakeClient())

    async def fake_lookup_deal(phone: str | None = None, deal_id: str | None = None):
        return {"ok": True, "data": {"deal_id": "D-99", "stage": "In progress"}, "error": None}

    monkeypatch.setitem(__import__("app.agent.agent", fromlist=["HANDLER_DISPATCH"]).HANDLER_DISPATCH, "lookup_deal", fake_lookup_deal)

    store = SessionStore()
    events = []
    async for event in run_agent("session-123", "Check my deal", store=store):
        events.append(event)

    assert any(event["type"] == "tool_start" and event["tool"] == "lookup_deal" for event in events)
    assert any(event["type"] == "tool_end" and event["tool"] == "lookup_deal" and event["ok"] is True for event in events)
    assert any(event["type"] == "token" and "relevant update" in event["text"] for event in events)
    assert any(event["type"] == "done" for event in events)


@pytest.mark.asyncio
async def test_get_vehicle_info_matches_normalized_model_names() -> None:
    """Vehicle matching should ignore case, spaces, and hyphen differences."""
    for candidate in ["XUV700", "xuv 700", "XUV-700"]:
        result = await __import__("app.tools.handlers", fromlist=["get_vehicle_info"]).get_vehicle_info(candidate)
        assert result["ok"] is True
        assert result["data"]["model"] == "XUV700"


@pytest.mark.asyncio
async def test_get_vehicle_info_handler_returns_ok_for_xuv700() -> None:
    """The direct handler call should return the XUV700 data with an indicative price."""
    result = await __import__("app.tools.handlers", fromlist=["get_vehicle_info"]).get_vehicle_info({"model": "XUV700"})
    assert result["ok"] is True
    assert result["data"] is not None
    assert "variants" in result["data"]
    assert any("₹" in variant["indicative_ex_showroom_price"] for variant in result["data"]["variants"])


@pytest.mark.asyncio
async def test_get_vehicle_info_direct_xuv700_returns_price() -> None:
    """The direct handler call for XUV700 should return real price data, not a generic failure."""
    result = await __import__("app.tools.handlers", fromlist=["get_vehicle_info"]).get_vehicle_info({"model": "XUV700"})
    assert result["ok"] is True, result
    assert result["data"]["model"] == "XUV700"
    assert any("indicative_ex_showroom_price" in variant for variant in result["data"]["variants"]) or any(
        "indicative_ex_showroom_price" in str(item) for item in result["data"]["variants"]
    )


@pytest.mark.asyncio
async def test_run_agent_calls_get_vehicle_info_for_xuv700_price_question(monkeypatch: pytest.MonkeyPatch) -> None:
    """The price question should trigger get_vehicle_info through the tool-call flow."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    seen = {}

    async def fake_get_vehicle_info(model: str, variant: str | None = None):
        seen["model"] = model
        seen["variant"] = variant
        return {
            "ok": True,
            "data": {"model": "XUV700", "variants": [{"name": "MX", "indicative_ex_showroom_price": "₹13.99L - ₹16.99L"}]},
            "error": None,
        }

    monkeypatch.setitem(__import__("app.agent.agent", fromlist=["HANDLER_DISPATCH"]).HANDLER_DISPATCH, "get_vehicle_info", fake_get_vehicle_info)

    class FakeFunction:
        def __init__(self, name: str, arguments: str):
            self.name = name
            self.arguments = arguments

    class FakeToolCallDelta:
        def __init__(self, index: int, function: FakeFunction, call_id: str):
            self.index = index
            self.id = call_id
            self.function = function

    class FakeDelta:
        def __init__(self, *, content: str | None = None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls or []

    class FakeChoice:
        def __init__(self, delta: FakeDelta):
            self.delta = delta

    class FakeChatChunk:
        def __init__(self, delta: FakeDelta):
            self.choices = [FakeChoice(delta)]

    class FakeStream:
        def __init__(self, payloads):
            self.payloads = payloads
            self._index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self.payloads):
                raise StopAsyncIteration
            payload = self.payloads[self._index]
            self._index += 1
            return payload

    class FakeCompletions:
        def __init__(self):
            self.calls = 0

        async def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return FakeStream(
                    [
                        FakeChatChunk(
                            FakeDelta(
                                tool_calls=[
                                    FakeToolCallDelta(
                                        0,
                                        FakeFunction("get_vehicle_info", '{"model":"XUV700"}'),
                                        "call_1",
                                    )
                                ]
                            )
                        )
                    ]
                )
            return FakeStream([
                FakeChatChunk(FakeDelta(content="The indicative ex-showroom range for the XUV700 is ₹13.99L - ₹16.99L.")),
            ])

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("app.agent.agent.AsyncOpenAI", lambda **kwargs: FakeClient())

    events = []
    async for event in __import__("app.agent.agent", fromlist=["run_agent"]).run_agent("session-price", "What's the price of the XUV700?"):
        events.append(event)

    assert seen["model"] == "XUV700"
    assert any(event["type"] == "tool_start" and event["tool"] == "get_vehicle_info" for event in events)
    assert any(event["type"] == "tool_end" and event["tool"] == "get_vehicle_info" and event["ok"] is True for event in events)
    assert any(event["type"] == "token" and "₹13.99L - ₹16.99L" in event["text"] for event in events)


@pytest.mark.asyncio
async def test_run_agent_handles_provider_error_and_yields_error_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider failures should yield a structured error event instead of crashing the streaming response."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    class FakeCompletions:
        async def create(self, **kwargs):
            raise Exception("The model does not exist or you do not have access to it.")

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("app.agent.agent.AsyncOpenAI", lambda **kwargs: FakeClient())

    events = []
    async for event in run_agent("session-999", "Check my deal"):
        events.append(event)

    assert any(event["type"] == "error" and "Groq model" in event["message"] for event in events)


@pytest.mark.asyncio
async def test_after_name_reply_is_single_phone_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """After receiving a name, the assistant should respond with one next-step message asking for phone."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    call_count = {"count": 0}

    class FakeDelta:
        def __init__(self, content: str | None = None):
            self.content = content
            self.tool_calls = []

    class FakeChoice:
        def __init__(self, delta: FakeDelta):
            self.delta = delta

    class FakeChatChunk:
        def __init__(self, delta: FakeDelta):
            self.choices = [FakeChoice(delta)]

    class FakeStream:
        def __init__(self, chunks):
            self.chunks = chunks
            self.idx = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.idx >= len(self.chunks):
                raise StopAsyncIteration
            item = self.chunks[self.idx]
            self.idx += 1
            return item

    class FakeCompletions:
        async def create(self, **kwargs):
            call_count["count"] += 1
            return FakeStream([FakeChatChunk(FakeDelta("Thanks, Aditi. Please share your 10-digit phone number."))])

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("app.agent.agent.AsyncOpenAI", lambda **kwargs: FakeClient())

    store = SessionStore()
    events = []
    async for event in run_agent("session-name", "Aditi Prasad", store=store):
        events.append(event)

    assert call_count["count"] == 1
    token_texts = [event["text"] for event in events if event.get("type") == "token"]
    assert len(token_texts) == 1
    assert "phone" in token_texts[0].lower()
    assert "[" not in token_texts[0]
    assert any(event["type"] == "done" for event in events)
