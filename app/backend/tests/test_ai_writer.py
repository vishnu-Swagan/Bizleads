"""AI-assisted wording must never become a second source of facts.

services/ai_writer.py sits next to services/outreach_composer.py under the
same rule: AI may improve WORDING, AI must never introduce a FACT. These
tests stub the HTTP boundary (no real network calls, matching the pattern in
tests/test_email_config.py::TestResendErrors and
tests/test_mapbox_keyword.py) and check the things that actually enforce
that rule:

  * with no ANTHROPIC_API_KEY, nothing pretends to be AI-assisted - every
    entry point reports unavailable, and the write endpoints answer 503
    rather than silently falling back to something the user could mistake
    for AI output.
  * a lead with no measured findings never gets a drafted email, whether the
    request never reaches the network (draft_for_category) or the router
    (409, "Qualify first").
  * the system prompt sent to the model explicitly forbids adding a claim,
    fact, statistic, or finding beyond what it was given.
  * a dead provider (network error, timeout, malformed response) degrades to
    None / 503, never an unhandled exception.
  * markdown fences the model adds are stripped from what reaches the user.
  * one user can never draft from another user's lead.
  * the API key itself is never echoed back in any response.
"""
import json

import httpx
import pytest

from models.leads import Leads
from services import ai_writer

FINDINGS = [
    {"id": "no_viewport", "label": "your site isn't mobile-friendly",
     "penalty": 30, "evidence": "No <meta name=viewport> tag found"},
    {"id": "no_https", "label": "your site isn't secure",
     "penalty": 20, "evidence": "Served over plain HTTP"},
]
FINDINGS_JSON = json.dumps(FINDINGS)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _configure(monkeypatch, key: str = "sk-ant-test-key-000"):
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)


async def _lead(db, **over):
    values = dict(
        user_id="user-a", business_name="Cafe Rossi", category="Cafe",
        location="Manchester", country="UK", website_url="http://caferossi.co.uk",
        website_score=42, contact_email="hi@caferossi.co.uk",
        findings=FINDINGS_JSON, pipeline_stage="new_lead",
    )
    values.update(over)
    lead = Leads(**values)
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


class _Recorder:
    """Captures every outbound Anthropic request and replies with a scripted
    response, installed at the same seam services/email_sender.py's tests use
    (monkeypatching the module's own `httpx.AsyncClient` attribute)."""

    def __init__(self, status: int = 200, text: str = "Polished text.", handler=None):
        self.status = status
        self.text = text
        self.calls: list[httpx.Request] = []
        self._handler = handler

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self._handler is not None:
            return self._handler(request)
        return httpx.Response(self.status, json={"content": [{"text": self.text}]})

    def install(self, monkeypatch):
        transport = httpx.MockTransport(self.handler)
        original = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        monkeypatch.setattr(ai_writer.httpx, "AsyncClient", factory)
        return self

    @property
    def last_body(self) -> dict:
        return json.loads(self.calls[-1].content)


# --- unconfigured means unavailable, everywhere -----------------------------

@pytest.mark.asyncio
async def test_is_ai_configured_is_false_with_no_key():
    assert ai_writer.is_ai_configured() is False


@pytest.mark.asyncio
async def test_polish_returns_none_when_unconfigured():
    assert await ai_writer.polish("please fix this email") is None


@pytest.mark.asyncio
async def test_draft_returns_none_when_unconfigured_even_with_findings():
    result = await ai_writer.draft_for_category("Cafe Rossi", "Cafe", FINDINGS)
    assert result is None


@pytest.mark.asyncio
async def test_polish_endpoint_503_when_unset(user_a_client):
    resp = await user_a_client.post("/api/v1/outreach/ai/polish", json={"text": "hi there"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_draft_endpoint_503_when_unset(user_a_client, db_session):
    lead = await _lead(db_session)
    resp = await user_a_client.post("/api/v1/outreach/ai/draft", json={"lead_id": lead.id})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_status_endpoint_reports_unavailable(user_a_client):
    resp = await user_a_client.get("/api/v1/outreach/ai/status")
    assert resp.status_code == 200
    assert resp.json() == {"available": False, "model": None}


@pytest.mark.asyncio
async def test_status_endpoint_reports_available_and_model(user_a_client, monkeypatch):
    _configure(monkeypatch)
    resp = await user_a_client.get("/api/v1/outreach/ai/status")
    body = resp.json()
    assert body["available"] is True
    assert body["model"] == ai_writer.MODEL


# --- no findings means no draft, same rule as the deterministic composer ---

@pytest.mark.asyncio
async def test_no_findings_returns_none_before_touching_the_network(monkeypatch):
    _configure(monkeypatch)
    recorder = _Recorder().install(monkeypatch)

    result = await ai_writer.draft_for_category("Cafe Rossi", "Cafe", [])

    assert result is None
    assert recorder.calls == [], "an empty findings list must never reach the network"


@pytest.mark.asyncio
async def test_draft_endpoint_409_when_lead_has_no_findings(user_a_client, db_session, monkeypatch):
    _configure(monkeypatch)
    lead = await _lead(db_session, findings=None)

    resp = await user_a_client.post("/api/v1/outreach/ai/draft", json={"lead_id": lead.id})

    assert resp.status_code in (409, 422)
    assert "qualify" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_draft_endpoint_409_when_findings_is_an_empty_list(user_a_client, db_session, monkeypatch):
    _configure(monkeypatch)
    lead = await _lead(db_session, findings="[]")

    resp = await user_a_client.post("/api/v1/outreach/ai/draft", json={"lead_id": lead.id})

    assert resp.status_code in (409, 422)


# --- the system prompt actually forbids adding facts ------------------------

@pytest.mark.asyncio
async def test_polish_system_prompt_forbids_adding_facts(monkeypatch):
    _configure(monkeypatch)
    recorder = _Recorder(text="Fixed text.").install(monkeypatch)

    await ai_writer.polish("i had a look at your site and it has issues")

    system = recorder.last_body["system"]
    assert "must not add any claim" in system.lower()
    assert "invent" in system.lower()
    assert recorder.last_body["model"] == ai_writer.MODEL


@pytest.mark.asyncio
async def test_draft_system_prompt_forbids_adding_facts_and_grounds_in_findings(monkeypatch):
    _configure(monkeypatch)
    recorder = _Recorder(text="SUBJECT: Hi\nBODY:\nHello there.").install(monkeypatch)

    await ai_writer.draft_for_category("Cafe Rossi", "Cafe", FINDINGS)

    system = recorder.last_body["system"]
    lowered = system.lower()
    assert "must not add any claim" in lowered
    assert "invent" in lowered
    assert "only facts you may" in lowered
    # The measured evidence must actually be in the prompt - this is the
    # grounding, not just an instruction not to fabricate.
    assert "no <meta name=viewport> tag found" in lowered
    assert "served over plain http" in lowered


@pytest.mark.asyncio
async def test_draft_prompt_tailors_register_by_category(monkeypatch):
    """A cafe and a law firm must not read the same instruction to the model."""
    _configure(monkeypatch)
    recorder = _Recorder(text="SUBJECT: Hi\nBODY:\nHello.").install(monkeypatch)

    await ai_writer.draft_for_category("Cafe Rossi", "Cafe", FINDINGS)
    cafe_system = recorder.last_body["system"]

    await ai_writer.draft_for_category("Smith & Co", "Law Firm", FINDINGS)
    law_system = recorder.last_body["system"]

    assert cafe_system != law_system
    assert "casual" in cafe_system.lower()
    assert "formal" in law_system.lower()


# --- provider failure degrades honestly, never raises -----------------------

@pytest.mark.asyncio
async def test_network_failure_returns_none_not_raises(monkeypatch):
    _configure(monkeypatch)

    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _Recorder(handler=_boom).install(monkeypatch)

    result = await ai_writer.polish("some text")

    assert result is None


@pytest.mark.asyncio
async def test_timeout_returns_none_not_raises(monkeypatch):
    _configure(monkeypatch)

    def _timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    _Recorder(handler=_timeout).install(monkeypatch)

    result = await ai_writer.draft_for_category("Cafe Rossi", "Cafe", FINDINGS)

    assert result is None


@pytest.mark.asyncio
async def test_a_non_200_response_returns_none(monkeypatch):
    _configure(monkeypatch)
    _Recorder(status=500, text="ignored").install(monkeypatch)

    assert await ai_writer.polish("some text") is None


@pytest.mark.asyncio
async def test_a_malformed_response_returns_none(monkeypatch):
    _configure(monkeypatch)

    def _malformed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    _Recorder(handler=_malformed).install(monkeypatch)

    assert await ai_writer.polish("some text") is None


@pytest.mark.asyncio
async def test_unparseable_draft_output_returns_none(monkeypatch):
    """A draft that doesn't come back as SUBJECT:/BODY: must not be guessed at."""
    _configure(monkeypatch)
    _Recorder(text="Just some prose with no structure at all.").install(monkeypatch)

    result = await ai_writer.draft_for_category("Cafe Rossi", "Cafe", FINDINGS)

    assert result is None


@pytest.mark.asyncio
async def test_provider_failure_surfaces_as_503_not_500(user_a_client, db_session, monkeypatch):
    _configure(monkeypatch)
    lead = await _lead(db_session)

    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _Recorder(handler=_boom).install(monkeypatch)

    resp = await user_a_client.post("/api/v1/outreach/ai/draft", json={"lead_id": lead.id})

    assert resp.status_code == 503


# --- markdown fences / preamble are stripped --------------------------------

@pytest.mark.asyncio
async def test_markdown_fences_are_stripped_from_polish(monkeypatch):
    _configure(monkeypatch)
    _Recorder(text="```\nHere is the corrected sentence.\n```").install(monkeypatch)

    result = await ai_writer.polish("here is the corected sentance")

    assert result is not None
    assert "```" not in result["text"]
    assert result["text"] == "Here is the corrected sentence."


@pytest.mark.asyncio
async def test_markdown_fences_are_stripped_from_draft_output(monkeypatch):
    _configure(monkeypatch)
    _Recorder(text="```\nSUBJECT: Quick note about your site\nBODY:\nHi there.\n```").install(monkeypatch)

    result = await ai_writer.draft_for_category("Cafe Rossi", "Cafe", FINDINGS)

    assert result is not None
    assert "```" not in result["subject"]
    assert "```" not in result["body_text"]
    assert result["subject"] == "Quick note about your site"
    assert result["body_text"] == "Hi there."


# --- ownership: one user cannot draft from another's lead -------------------

@pytest.mark.asyncio
async def test_other_users_lead_is_not_found(user_b_client, db_session, monkeypatch):
    _configure(monkeypatch)
    lead = await _lead(db_session)  # owned by user-a

    resp = await user_b_client.post("/api/v1/outreach/ai/draft", json={"lead_id": lead.id})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_nonexistent_lead_is_not_found(user_a_client, monkeypatch):
    _configure(monkeypatch)

    resp = await user_a_client.post("/api/v1/outreach/ai/draft", json={"lead_id": 999999})

    assert resp.status_code == 404


# --- the key is never echoed back --------------------------------------

SECRET_KEY = "sk-ant-super-secret-value-do-not-leak"


@pytest.mark.asyncio
async def test_key_never_appears_in_status_response(user_a_client, monkeypatch):
    _configure(monkeypatch, key=SECRET_KEY)

    resp = await user_a_client.get("/api/v1/outreach/ai/status")

    assert SECRET_KEY not in resp.text


@pytest.mark.asyncio
async def test_key_never_appears_in_a_successful_polish_response(user_a_client, monkeypatch):
    _configure(monkeypatch, key=SECRET_KEY)
    _Recorder(text="Fixed text.").install(monkeypatch)

    resp = await user_a_client.post("/api/v1/outreach/ai/polish", json={"text": "fix me"})

    assert SECRET_KEY not in resp.text


@pytest.mark.asyncio
async def test_key_never_appears_in_a_failed_response(user_a_client, monkeypatch):
    _configure(monkeypatch, key=SECRET_KEY)

    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _Recorder(handler=_boom).install(monkeypatch)

    resp = await user_a_client.post("/api/v1/outreach/ai/polish", json={"text": "fix me"})

    assert resp.status_code == 503
    assert SECRET_KEY not in resp.text


# --- a couple of happy-path shape checks -------------------------------

@pytest.mark.asyncio
async def test_a_successful_polish_reports_changed(monkeypatch):
    _configure(monkeypatch)
    _Recorder(text="This is the polished version.").install(monkeypatch)

    result = await ai_writer.polish("this is teh rough draft")

    assert result == {"text": "This is the polished version.", "changed": True}


@pytest.mark.asyncio
async def test_a_successful_draft_via_the_endpoint(user_a_client, db_session, monkeypatch):
    _configure(monkeypatch)
    lead = await _lead(db_session)
    _Recorder(text="SUBJECT: Your site on mobile\nBODY:\nHi there, quick note.").install(monkeypatch)

    resp = await user_a_client.post("/api/v1/outreach/ai/draft", json={"lead_id": lead.id})

    assert resp.status_code == 200
    body = resp.json()
    assert body["subject"] == "Your site on mobile"
    assert body["body_text"] == "Hi there, quick note."
    assert body["ai_available"] is True
    assert body["lead_id"] == lead.id
