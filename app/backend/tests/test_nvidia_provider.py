"""NVIDIA NIM as an alternative provider.

NIM speaks the OpenAI chat-completions dialect, so it needs no bespoke
client — a different URL, auth header and response path. What must NOT differ
is the constraint that makes this feature safe: the model may improve wording
and may never introduce a fact. A weaker free model makes that MORE important,
not less, because it follows instructions less reliably than Claude does.
"""
import httpx
import pytest

from services import ai_writer

FINDING = {"id": "no_viewport", "label": "Not mobile-friendly",
           "evidence": "No <meta name=viewport>"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "NVIDIA_API_KEY", "NVIDIA_MODEL"):
        monkeypatch.delenv(var, raising=False)


def _stub(monkeypatch, capture=None, *, status=200, body=None):
    payload = body if body is not None else {
        "choices": [{"message": {"content": "SUBJECT: Test\nBODY: Hello there."}}]
    }

    def handler(request):
        if capture is not None:
            capture["url"] = str(request.url)
            capture["headers"] = dict(request.headers)
            capture["body"] = httpx.Response(200, content=request.content).json()
        return httpx.Response(status, json=payload)

    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        ai_writer.httpx, "AsyncClient",
        lambda *a, **k: original(*a, **{**k, "transport": transport}),
    )


class TestProviderSelection:
    def test_an_nvidia_key_alone_enables_ai(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        assert ai_writer.is_ai_configured() is True
        assert ai_writer.active_model() == ai_writer.DEFAULT_NVIDIA_MODEL

    def test_anthropic_wins_when_both_are_set(self, monkeypatch):
        """Claude follows the anti-fabrication rule far more reliably, and
        that rule is the only thing keeping this feature honest."""
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        assert ai_writer._provider()[0] == "anthropic"

    def test_the_model_is_overridable(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setenv("NVIDIA_MODEL", "qwen/qwen2.5-coder-32b-instruct")
        assert ai_writer.active_model() == "qwen/qwen2.5-coder-32b-instruct"


class TestTheStatusEndpointNamesTheRealModel:
    """The badge in the UI must name the model that actually ran.

    /ai/status used to return the module's MODEL constant, which is the
    Anthropic model name specifically. With only an NVIDIA key set, the
    endpoint therefore announced "claude-sonnet-5" while every request went to
    NVIDIA — the app misreporting its own behaviour, which is the failure mode
    this codebase exists to avoid.
    """

    @pytest.mark.asyncio
    async def test_it_reports_the_nvidia_model_not_the_anthropic_constant(
        self, user_a_client, monkeypatch
    ):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")

        body = (await user_a_client.get("/api/v1/outreach/ai/status")).json()

        assert body["available"] is True
        assert body["model"] == ai_writer.DEFAULT_NVIDIA_MODEL
        assert body["model"] != ai_writer.MODEL, (
            "reporting the Anthropic constant while NVIDIA serves the request "
            "is the exact regression this guards"
        )

    @pytest.mark.asyncio
    async def test_it_reports_an_override(self, user_a_client, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setenv("NVIDIA_MODEL", "qwen/qwen2.5-coder-32b-instruct")

        body = (await user_a_client.get("/api/v1/outreach/ai/status")).json()

        assert body["model"] == "qwen/qwen2.5-coder-32b-instruct"


class TestTheRequest:
    @pytest.mark.asyncio
    async def test_it_uses_openai_shape_and_bearer_auth(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-secret")
        capture: dict = {}
        _stub(monkeypatch, capture)

        await ai_writer.polish("we should of fixed this")

        assert "integrate.api.nvidia.com" in capture["url"]
        assert capture["headers"]["authorization"] == "Bearer nvapi-secret"
        roles = [m["role"] for m in capture["body"]["messages"]]
        assert roles == ["system", "user"], "system prompt must be a system message"

    @pytest.mark.asyncio
    async def test_the_anti_fabrication_rules_are_still_sent(self, monkeypatch):
        """The guarantee must not weaken just because the provider changed."""
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        capture: dict = {}
        _stub(monkeypatch, capture)

        await ai_writer.polish("hello")

        system = capture["body"]["messages"][0]["content"]
        assert "must not" in system.lower()
        assert "fabricate" in system.lower() or "invent" in system.lower()

    @pytest.mark.asyncio
    async def test_sampling_is_conservative(self, monkeypatch):
        """A creative sampler is what starts adding flattering details."""
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        capture: dict = {}
        _stub(monkeypatch, capture)

        await ai_writer.polish("hello")

        assert capture["body"]["temperature"] <= 0.3


class TestItStillFailsSafe:
    @pytest.mark.asyncio
    async def test_no_findings_means_no_draft_and_no_call(self, monkeypatch):
        """The invariant that survives every provider change."""
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        called = {"n": 0}

        def handler(request):
            called["n"] += 1
            return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

        original = httpx.AsyncClient
        monkeypatch.setattr(
            ai_writer.httpx, "AsyncClient",
            lambda *a, **k: original(*a, **{**k, "transport": httpx.MockTransport(handler)}),
        )

        result = await ai_writer.draft_for_category("Cafe Rossi", "Cafe", [])

        assert result is None
        assert called["n"] == 0, "the provider was called with nothing measured"

    @pytest.mark.asyncio
    async def test_a_provider_error_degrades_rather_than_raises(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        _stub(monkeypatch, status=500, body={"error": "upstream"})

        assert await ai_writer.polish("hello") is None

    @pytest.mark.asyncio
    async def test_a_malformed_response_degrades(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        _stub(monkeypatch, body={"unexpected": "shape"})

        assert await ai_writer.polish("hello") is None

    @pytest.mark.asyncio
    async def test_the_key_never_appears_in_output(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-super-secret")
        _stub(monkeypatch)

        result = await ai_writer.polish("hello")

        assert "nvapi-super-secret" not in str(result)
