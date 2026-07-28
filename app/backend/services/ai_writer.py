"""AI-assisted wording for outreach emails - never a source of facts.

services/outreach_composer.py explains why there is no language model in the
deterministic composer: every claim in outreach must trace to a measurement
in services/site_signals.py, and a whole AI lead-generation path was deleted
earlier for exactly this reason (see
tests/test_discovery.py::test_the_fabrication_path_does_not_exist).

This module does not relax that rule - it adds a second capability on top of
it. AI here is allowed to touch WORDING only:

  * `polish` takes text the USER wrote and fixes grammar, clarity and tone.
    It is never shown anything the user did not already write, and it is
    told, explicitly, not to add a single new claim.
  * `draft_for_category` takes MEASURED FINDINGS (the same objects
    outreach_composer reads from services/site_signals.py) and asks the
    model to write an opening email using only those findings as fact,
    tailored in register to the business category. A lead with no findings
    gets no draft - same rule as the composer, for the same reason: no
    honest measurement, no honest email.

Every model call is instructed, in its system prompt, that it may reword but
must never invent a claim, statistic, promise, or finding. That instruction
is enforced by prompting, not by code - which is exactly why the tests for
this module assert on the literal text of the system prompt sent, not just
on the shape of the response.

The Anthropic API key is read from os.environ at CALL TIME in every function
that needs it, never cached in a module-level constant. That pattern - a key
frozen at import time - has caused three production bugs in this codebase
already (see services/email_sender.py's docstring and
tests/test_email_config.py for the same lesson learned the hard way with
SMTP credentials).

The HTTP call is raw httpx against the Anthropic Messages API, not the
`anthropic` SDK: httpx is already a dependency of this project and the
Messages API surface this module needs is a single POST.

Every call has a timeout, and every failure - missing key, network error,
timeout, malformed response, an answer that doesn't parse into the shape we
asked for - returns None instead of raising. A dead or misbehaving AI
provider must degrade outreach back to "no AI assist available", never crash
the request that was trying to use it.
"""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
# Fixed model choice. Not env-driven, so no third repeat of the "config only
# takes effect after a restart" class of bug this module explicitly avoids
# for the one value that genuinely does change per environment: the key.
MODEL = "claude-sonnet-5"

_REQUEST_TIMEOUT_SECONDS = 30.0
_MAX_TOKENS = 1024
_DEFAULT_TONE = "professional"


def is_ai_configured() -> bool:
    """Whether an Anthropic key is present right now, read fresh each call."""
    return bool(_provider()[1])


# NVIDIA's hosted NIM catalogue speaks the OpenAI chat-completions dialect, so
# it needs no bespoke client — only a different base URL, auth header and
# response shape. Any other OpenAI-compatible endpoint works through the same
# path by setting OPENAI_BASE_URL.
NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"


def _provider() -> tuple[str, str]:
    """Which provider to use, and its key. Chosen by what is configured.

    Anthropic wins when both are present because it follows the
    anti-fabrication instruction markedly more reliably, and that instruction
    is the only thing standing between this feature and the invented claims
    the product exists to avoid.
    """
    anthropic = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if anthropic:
        return "anthropic", anthropic
    nvidia = os.environ.get("NVIDIA_API_KEY", "").strip()
    if nvidia:
        return "nvidia", nvidia
    return "none", ""


def active_model() -> Optional[str]:
    """The model that would actually be used, for the status endpoint."""
    name, key = _provider()
    if name == "anthropic":
        return MODEL
    if name == "nvidia":
        return os.environ.get("NVIDIA_MODEL", "").strip() or DEFAULT_NVIDIA_MODEL
    return None


# --- category-specific register -------------------------------------------
#
# This is a deterministic lookup, not something left to the model to guess.
# "Address a cafe differently from a law firm" is a hard requirement, and a
# hand-picked mapping is a fact about *tone*, not about the business - it
# never claims anything about the specific recipient, so it is safe to feed
# to the model as an instruction rather than as something it could confuse
# for evidence.
_CATEGORY_GUIDANCE: List[tuple] = [
    ("cafe", "warm, casual and friendly - like a regular chatting with the owner"),
    ("coffee", "warm, casual and friendly - like a regular chatting with the owner"),
    ("restaurant", "warm and casual, respectful of how busy the kitchen and front-of-house are"),
    ("bar", "casual and direct, no corporate jargon"),
    ("bakery", "warm and casual, friendly neighbourhood tone"),
    ("law", "formal, precise and respectful of their time - no slang, no exclamation points"),
    ("legal", "formal, precise and respectful of their time - no slang, no exclamation points"),
    ("attorney", "formal, precise and respectful of their time - no slang, no exclamation points"),
    ("account", "formal and precise, numbers-minded, respectful of their time"),
    ("dental", "professional but approachable, mindful this is a healthcare practice"),
    ("dentist", "professional but approachable, mindful this is a healthcare practice"),
    ("medical", "professional, careful and mindful this is a healthcare practice"),
    ("clinic", "professional, careful and mindful this is a healthcare practice"),
    ("salon", "friendly and personable, like a satisfied client"),
    ("spa", "calm, friendly and personable"),
    ("contractor", "direct and practical, respectful of a busy trades schedule"),
    ("plumb", "direct and practical, respectful of a busy trades schedule"),
    ("electric", "direct and practical, respectful of a busy trades schedule"),
    ("construction", "direct and practical, respectful of a busy trades schedule"),
    ("retail", "friendly and upbeat, aware retail owners are busy on the shop floor"),
    ("real estate", "professional and polished, aware they are used to being pitched to"),
    ("realtor", "professional and polished, aware they are used to being pitched to"),
    ("gym", "energetic but respectful, casual"),
    ("fitness", "energetic but respectful, casual"),
]
_DEFAULT_GUIDANCE = "professional, friendly and respectful of a busy small-business owner's time"


def _guidance_for_category(category: str) -> str:
    cat = (category or "").strip().lower()
    for key, guidance in _CATEGORY_GUIDANCE:
        if key in cat:
            return guidance
    return _DEFAULT_GUIDANCE


def _findings_block(findings: List[Dict[str, Any]]) -> str:
    """The only facts the model is allowed to reference, one line each."""
    lines: List[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        label = finding.get("label") or finding.get("id") or "issue"
        evidence = (finding.get("evidence") or "").strip()
        line = f"- {label}"
        if evidence:
            line += f" (measured: {evidence})"
        lines.append(line)
    return "\n".join(lines) if lines else "(no findings supplied)"


_ANTI_FABRICATION_RULES = (
    "You must not add any claim, fact, statistic, promise, guarantee, price, "
    "or detail that is not already present in the material given to you. "
    "You must not invent findings, and you must not claim to have personally "
    "visited, browsed, or tested anything beyond what is stated. Do not "
    "praise the business for anything that isn't evidenced in what you were "
    "given. If you are unsure whether something is supported by the input, "
    "leave it out rather than fabricate it."
)


def _polish_system_prompt(tone: str, findings: List[Dict[str, Any]]) -> str:
    findings_note = ""
    if findings:
        findings_note = (
            "\n\nFor reference only, here are the measured findings this email "
            "may already be referring to. Use them only to confirm a claim "
            "already written by the user is accurate - never to add a new "
            "claim the user did not write themselves:\n" + _findings_block(findings)
        )
    return (
        "You are a copy editor for a short cold-outreach email written by a "
        "small-business salesperson. Your ONLY job is to fix grammar, "
        "spelling, clarity and tone in the text you are given, in a "
        f"{tone or _DEFAULT_TONE} register. Do not change the meaning of any "
        "sentence, and do not add new sentences unless they only restate "
        "something already said more clearly.\n\n"
        + _ANTI_FABRICATION_RULES
        + findings_note
        + "\n\nReturn ONLY the corrected text - no preamble, no markdown code "
        "fences, no explanation, no quotation marks around the result."
    )


def _draft_system_prompt(
    *,
    business_name: str,
    category: str,
    findings: List[Dict[str, Any]],
    sender_name: str,
    sender_business: str,
    tone: str,
) -> str:
    sender_bits = " ".join(
        part for part in (sender_name.strip(), sender_business.strip()) if part
    )
    sender_line = f"You are writing on behalf of {sender_bits}." if sender_bits else (
        "You are writing on behalf of a website consultant reaching out cold."
    )
    guidance = _guidance_for_category(category)
    return (
        "You are drafting a short, honest, cold outreach email to the owner "
        f"of a business called \"{business_name}\" (category: "
        f"{category or 'unknown'}). {sender_line}\n\n"
        "You will be given a list of MEASURED FINDINGS about their website "
        "below. These are the ONLY facts you may state about the business or "
        "its website anywhere in the email.\n\n"
        + _ANTI_FABRICATION_RULES
        + "\n\nMeasured findings (the ONLY facts you may reference - do not "
        "reference any issue not listed here):\n" + _findings_block(findings)
        + f"\n\nWrite in a register appropriate for a {category or 'small'} "
        f"business owner: {guidance}. Overall tone preference: "
        f"{tone or _DEFAULT_TONE}. Keep it short (under 150 words in the "
        "body). End with a soft, low-pressure call to action - do not pitch "
        "a specific price or make a guarantee.\n\n"
        "Output format, exactly:\n"
        "SUBJECT: <subject line>\n"
        "BODY:\n"
        "<email body>\n\n"
        "No preamble, no markdown code fences, no explanation outside that "
        "format."
    )


# --- markdown fence / preamble stripping -----------------------------------

_PREAMBLE_RE = re.compile(
    r"^(here('|’)?s|sure|certainly|okay|below is|i('|’)?ve|i have)"
    r".{0,80}:\s*$",
    re.IGNORECASE,
)


def _clean_model_text(raw: str) -> str:
    text = (raw or "").strip()

    if text.startswith("```"):
        # Drop the opening fence line (``` or ```lang) and a trailing fence.
        first_newline = text.find("\n")
        text = text[first_newline + 1:] if first_newline != -1 else ""
        stripped = text.rstrip()
        if stripped.endswith("```"):
            text = stripped[: -3]
        text = text.strip()

    lines = text.split("\n", 1)
    if len(lines) == 2 and _PREAMBLE_RE.match(lines[0].strip()):
        text = lines[1].lstrip("\n").strip()

    return text.strip()


_SUBJECT_RE = re.compile(r"^SUBJECT:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_BODY_RE = re.compile(r"BODY:\s*(.*)\Z", re.IGNORECASE | re.DOTALL)


def _parse_subject_body(text: str) -> Optional[Dict[str, str]]:
    subject_match = _SUBJECT_RE.search(text)
    body_match = _BODY_RE.search(text)
    if not subject_match or not body_match:
        return None
    subject = subject_match.group(1).strip()
    body = body_match.group(1).strip()
    if not subject or not body:
        return None
    return {"subject": subject, "body_text": body}


# --- the one HTTP call point ------------------------------------------------

async def _call_nvidia(api_key: str, system: str, user_content: str) -> Optional[str]:
    """POST to NVIDIA NIM, which speaks OpenAI chat-completions.

    The system prompt becomes a system message rather than a top-level field,
    and the text sits at choices[0].message.content. Everything else — the
    anti-fabrication rules, the findings block, the degrade-on-failure
    contract — is identical, because those live above this layer.
    """
    body = {
        "model": active_model(),
        "max_tokens": _MAX_TOKENS,
        # Low temperature deliberately. This task is constrained rewriting,
        # not invention, and a creative sampler is exactly what starts adding
        # flattering details nobody measured.
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                NVIDIA_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        text = data["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001 - must degrade, never raise
        logger.exception("NVIDIA NIM call failed; degrading to no AI assist")
        return None

    return _clean_model_text(text) if isinstance(text, str) else None


async def _call_anthropic(system: str, user_content: str) -> Optional[str]:
    """POST to whichever provider is configured. Returns text, or None.

    Keeps its original name because every caller and test already uses it;
    the provider choice happens here rather than at each call site.
    """
    provider, api_key = _provider()
    if not api_key:
        return None
    if provider == "nvidia":
        return await _call_nvidia(api_key, system, user_content)

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": MODEL,
        "max_tokens": _MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user_content}],
    }

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(ANTHROPIC_API_URL, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        text = data["content"][0]["text"]
    except Exception:  # noqa: BLE001 - any failure here must degrade, not raise
        logger.exception("Anthropic API call failed; degrading to no AI assist")
        return None

    if not isinstance(text, str):
        return None
    return _clean_model_text(text)


# --- public API --------------------------------------------------------

async def polish(
    text: str,
    *,
    tone: str = _DEFAULT_TONE,
    findings: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Fix grammar/clarity/tone of text the USER wrote. Adds no new claims.

    Returns {"text": ..., "changed": bool}, or None if AI is unavailable
    (unconfigured, or the call failed) - never raises.
    """
    if not is_ai_configured():
        return None

    original = text or ""
    if not original.strip():
        return {"text": original, "changed": False}

    system = _polish_system_prompt(tone or _DEFAULT_TONE, findings or [])
    result = await _call_anthropic(system, original)
    if result is None:
        return None

    return {"text": result, "changed": result.strip() != original.strip()}


async def draft_for_category(
    business_name: str,
    category: str,
    findings: List[Dict[str, Any]],
    *,
    sender_name: str = "",
    sender_business: str = "",
    tone: str = _DEFAULT_TONE,
) -> Optional[Dict[str, Any]]:
    """Draft an opening email grounded ONLY in the supplied findings.

    No findings means no honest email - same rule as
    services/outreach_composer.py - so this returns None before ever
    touching the network. Returns {"subject": ..., "body_text": ...}, or
    None if there is nothing to draft or the AI call failed.
    """
    if not findings:
        return None
    if not is_ai_configured():
        return None

    system = _draft_system_prompt(
        business_name=business_name or "the business",
        category=category or "",
        findings=findings,
        sender_name=sender_name or "",
        sender_business=sender_business or "",
        tone=tone or _DEFAULT_TONE,
    )
    result = await _call_anthropic(system, "Write the email now.")
    if result is None:
        return None

    return _parse_subject_body(result)
