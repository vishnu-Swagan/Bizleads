"""The AI "how to win this lead" note.

This note is the one piece of AI output in the product that is allowed to
recommend rather than only restate — it is read by the person selling and
never sent to the prospect. That freedom is exactly why its fence needs
testing: the model may propose an angle, and may not invent a fact to justify
one.

The rule it shares with every other AI path here: no measured findings means
no note at all, never a generic one.
"""
import json

import pytest

from models.lead_notes import Lead_notes
from models.leads import Leads
from services import ai_writer
from services.lead_angle import parse_findings, write_angle_note
from sqlalchemy import select
from tests.conftest import USER_A_ID

FINDINGS = [
    {"id": "no_viewport", "label": "Not mobile-friendly", "penalty": 30,
     "evidence": "No <meta name='viewport'>", "category": "mobile"},
    {"id": "no_analytics", "label": "No analytics installed", "penalty": 4,
     "evidence": "No Google Analytics or Tag Manager", "category": "marketing"},
]


@pytest.fixture(autouse=True)
def _no_provider(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "NVIDIA_API_KEY", "NVIDIA_MODEL"):
        monkeypatch.delenv(var, raising=False)


async def _lead(db_session, *, findings=json.dumps(FINDINGS), user_id=USER_A_ID):
    lead = Leads(
        user_id=user_id, business_name="Riverside Cafe", category="Cafe",
        location="Leeds", country="United Kingdom", findings=findings,
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    return lead


class TestParseFindings:
    def test_null_and_empty_both_mean_nothing_to_work_from(self):
        assert parse_findings(None) == []
        assert parse_findings("[]") == []

    def test_malformed_json_is_not_guessed_at(self):
        assert parse_findings("{not json") == []
        assert parse_findings('{"a": 1}') == [], "an object is not a findings list"


class TestItRefusesWhenThereIsNothingHonestToSay:
    async def test_no_findings_means_no_note(self, db_session, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        called = False

        async def _fail(*a, **k):
            nonlocal called
            called = True
            return "should never be reached"

        monkeypatch.setattr(ai_writer, "_call_anthropic", _fail)

        lead = await _lead(db_session, findings=None)
        assert await write_angle_note(db_session, lead, USER_A_ID) is None
        assert not called, "a lead with no findings must not reach the model at all"

    async def test_no_provider_means_no_note(self, db_session):
        lead = await _lead(db_session)
        assert await write_angle_note(db_session, lead, USER_A_ID) is None

    async def test_a_failed_call_writes_nothing(self, db_session, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")

        async def _dead(*a, **k):
            return None

        monkeypatch.setattr(ai_writer, "_call_anthropic", _dead)

        lead = await _lead(db_session)
        assert await write_angle_note(db_session, lead, USER_A_ID) is None
        notes = (await db_session.execute(select(Lead_notes))).scalars().all()
        assert notes == [], "a failed call must not leave a half-written note"

    async def test_an_unexpected_error_does_not_escape(self, db_session, monkeypatch):
        """A note is never worth failing the paid qualification that produced it."""
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")

        async def _boom(*a, **k):
            raise RuntimeError("provider exploded")

        monkeypatch.setattr(ai_writer, "_call_anthropic", _boom)

        lead = await _lead(db_session)
        assert await write_angle_note(db_session, lead, USER_A_ID) is None


class TestTheStoredNote:
    @pytest.fixture(autouse=True)
    def _working_provider(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        self.prompts: list = []

        async def _reply(system, user_content):
            self.prompts.append(system)
            return "Lead with the mobile issue — they can check it on their own phone."

        monkeypatch.setattr(ai_writer, "_call_anthropic", _reply)

    async def test_it_is_stored_against_the_lead_and_tagged(self, db_session):
        lead = await _lead(db_session)
        note = await write_angle_note(db_session, lead, USER_A_ID)
        await db_session.commit()

        assert note
        stored = (await db_session.execute(select(Lead_notes))).scalars().all()
        assert len(stored) == 1
        assert stored[0].lead_id == lead.id
        assert stored[0].note_type == ai_writer.AI_ANGLE_NOTE_TYPE
        assert stored[0].content == note

    async def test_regenerating_replaces_rather_than_stacks(self, db_session):
        lead = await _lead(db_session)
        await write_angle_note(db_session, lead, USER_A_ID)
        await db_session.commit()
        await write_angle_note(db_session, lead, USER_A_ID)
        await db_session.commit()

        stored = (await db_session.execute(select(Lead_notes))).scalars().all()
        assert len(stored) == 1, "a re-run must leave one current note, not a pile"

    async def test_it_never_deletes_a_human_note(self, db_session):
        lead = await _lead(db_session)
        db_session.add(Lead_notes(
            user_id=USER_A_ID, lead_id=lead.id,
            content="Spoke to the owner on Tuesday", note_type="note",
        ))
        await db_session.commit()

        await write_angle_note(db_session, lead, USER_A_ID)
        await db_session.commit()

        contents = {
            n.content for n in (await db_session.execute(select(Lead_notes))).scalars().all()
        }
        assert "Spoke to the owner on Tuesday" in contents

    async def test_the_prompt_carries_the_anti_fabrication_rules(self, db_session):
        """The note may recommend an approach; it may not invent a fact to
        justify one. That distinction lives entirely in the prompt, so the
        prompt is what gets asserted on."""
        lead = await _lead(db_session)
        await write_angle_note(db_session, lead, USER_A_ID)

        system = self.prompts[0].lower()
        assert "revenue" in system and "competitors" in system, \
            "the note-specific speculation ban must be present"
        assert "internal" in system, "the model must know this is not sent to the prospect"
        for banned in ("only facts", "measured findings"):
            assert banned in system

    async def test_only_the_measured_findings_are_shown_to_the_model(self, db_session):
        lead = await _lead(db_session)
        await write_angle_note(db_session, lead, USER_A_ID)

        system = self.prompts[0]
        assert "Not mobile-friendly" in system
        assert "No analytics installed" in system
