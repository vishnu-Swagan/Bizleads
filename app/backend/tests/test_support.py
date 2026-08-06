"""The operators' request queue.

Two audiences with two authentication schemes share one queue, so most of
what matters here is that neither can be reached the other's way and that
neither is reachable by nobody in particular.

The engineer side is a shared secret rather than a session because whoever is
working on the product does so from a terminal and has no account in this
application. That makes an unset secret the dangerous case, and it is tested
first: these requests describe what is broken and how, which is a useful map
for anybody who should not have it.
"""
import pytest

from tests.conftest import USER_A_EMAIL

SECRET = "test-support-secret"


@pytest.fixture
def as_admin(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", USER_A_EMAIL)


@pytest.fixture
def agent_secret(monkeypatch):
    monkeypatch.setenv("SUPPORT_AGENT_SECRET", SECRET)


async def _raise(client, title="Export is wrong", **extra):
    payload = {"title": title, "body": "The phone column is empty.", "priority": "normal"}
    payload.update(extra)
    response = await client.post("/api/v1/support", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


class TestWhoMayReachTheQueue:
    async def test_a_non_admin_cannot_read_requests(self, user_a_client, monkeypatch):
        monkeypatch.delenv("ADMIN_EMAILS", raising=False)
        assert (await user_a_client.get("/api/v1/support")).status_code == 403

    async def test_a_non_admin_cannot_raise_one(self, user_a_client, monkeypatch):
        monkeypatch.delenv("ADMIN_EMAILS", raising=False)
        response = await user_a_client.post("/api/v1/support", json={"title": "hello"})
        assert response.status_code == 403

    async def test_the_agent_queue_is_closed_when_no_secret_is_set(
        self, anon_client, monkeypatch
    ):
        """Unset must disable it, not open it.

        The failure mode being guarded is a deployment that has never heard of
        the variable publishing every request the operators have filed.
        """
        monkeypatch.delenv("SUPPORT_AGENT_SECRET", raising=False)
        response = await anon_client.get("/api/v1/support/agent/queue")
        assert response.status_code == 401
        assert "not set" in response.json()["detail"]

    async def test_a_wrong_secret_is_refused(self, anon_client, agent_secret):
        response = await anon_client.get(
            "/api/v1/support/agent/queue", headers={"X-Support-Secret": "wrong"}
        )
        assert response.status_code == 401

    async def test_no_secret_at_all_is_refused(self, anon_client, agent_secret):
        assert (await anon_client.get("/api/v1/support/agent/queue")).status_code == 401

    async def test_the_right_secret_is_admitted(self, anon_client, agent_secret):
        response = await anon_client.get(
            "/api/v1/support/agent/queue", headers={"X-Support-Secret": SECRET}
        )
        assert response.status_code == 200

    async def test_an_admin_session_does_not_open_the_agent_route(
        self, user_a_client, as_admin, monkeypatch
    ):
        """Two schemes, neither substituting for the other."""
        monkeypatch.delenv("SUPPORT_AGENT_SECRET", raising=False)
        assert (await user_a_client.get("/api/v1/support/agent/queue")).status_code == 401


class TestRaisingAndThreading:
    async def test_a_request_is_stored_with_its_author(self, user_a_client, as_admin):
        ticket = await _raise(user_a_client)
        assert ticket["title"] == "Export is wrong"
        assert ticket["status"] == "open"
        assert ticket["created_by_email"] == USER_A_EMAIL

    async def test_messages_thread_in_order(self, user_a_client, as_admin):
        ticket = await _raise(user_a_client)

        for text in ("First note", "Second note"):
            response = await user_a_client.post(
                f"/api/v1/support/{ticket['id']}/messages", json={"body": text}
            )
            assert response.status_code == 201

        body = (await user_a_client.get(f"/api/v1/support/{ticket['id']}")).json()
        assert [m["body"] for m in body["messages"]] == ["First note", "Second note"]
        assert all(m["author_type"] == "operator" for m in body["messages"])

    async def test_an_invalid_priority_is_refused(self, user_a_client, as_admin):
        response = await user_a_client.post(
            "/api/v1/support", json={"title": "x", "priority": "urgent-ish"}
        )
        assert response.status_code == 400

    async def test_an_empty_message_is_refused(self, user_a_client, as_admin):
        ticket = await _raise(user_a_client)
        response = await user_a_client.post(
            f"/api/v1/support/{ticket['id']}/messages", json={"body": ""}
        )
        assert response.status_code == 422

    async def test_replying_to_a_resolved_request_reopens_it(self, user_a_client, as_admin):
        """Otherwise "this is still happening" lands in an archive nobody reads."""
        ticket = await _raise(user_a_client)
        await user_a_client.post(
            f"/api/v1/support/{ticket['id']}/status", json={"status": "resolved"}
        )

        body = (await user_a_client.post(
            f"/api/v1/support/{ticket['id']}/messages", json={"body": "Still broken"}
        )).json()

        assert body["status"] == "open"
        assert body["resolved_at"] is None

    async def test_an_unknown_request_is_a_404(self, user_a_client, as_admin):
        assert (await user_a_client.get("/api/v1/support/9999")).status_code == 404


class TestTheEngineerSide:
    async def test_the_queue_carries_the_whole_thread(
        self, user_a_client, anon_client, as_admin, agent_secret
    ):
        """The title says "export is wrong"; the thread says which column."""
        ticket = await _raise(user_a_client)
        await user_a_client.post(
            f"/api/v1/support/{ticket['id']}/messages",
            json={"body": "Specifically the Phone column"},
        )

        body = (await anon_client.get(
            "/api/v1/support/agent/queue", headers={"X-Support-Secret": SECRET}
        )).json()

        assert body["count"] == 1
        assert body["items"][0]["messages"][0]["body"] == "Specifically the Phone column"

    async def test_resolved_requests_are_not_in_the_queue(
        self, user_a_client, anon_client, as_admin, agent_secret
    ):
        ticket = await _raise(user_a_client)
        await user_a_client.post(
            f"/api/v1/support/{ticket['id']}/status", json={"status": "resolved"}
        )

        body = (await anon_client.get(
            "/api/v1/support/agent/queue", headers={"X-Support-Secret": SECRET}
        )).json()
        assert body["count"] == 0

    async def test_a_reply_lands_on_the_thread_marked_as_engineering(
        self, user_a_client, anon_client, as_admin, agent_secret
    ):
        ticket = await _raise(user_a_client)

        response = await anon_client.post(
            f"/api/v1/support/agent/{ticket['id']}/reply",
            json={"body": "Fixed and deployed in 3bd347a"},
            headers={"X-Support-Secret": SECRET},
        )

        assert response.status_code == 200
        message = response.json()["messages"][-1]
        assert message["author_type"] == "engineer"
        assert "3bd347a" in message["body"]

    async def test_a_reply_can_resolve_the_request(
        self, user_a_client, anon_client, as_admin, agent_secret
    ):
        ticket = await _raise(user_a_client)

        body = (await anon_client.post(
            f"/api/v1/support/agent/{ticket['id']}/reply?status=resolved",
            json={"body": "Done"},
            headers={"X-Support-Secret": SECRET},
        )).json()

        assert body["status"] == "resolved"
        assert body["resolved_at"] is not None

    async def test_a_reply_without_the_secret_is_refused(
        self, user_a_client, anon_client, as_admin, agent_secret
    ):
        ticket = await _raise(user_a_client)
        response = await anon_client.post(
            f"/api/v1/support/agent/{ticket['id']}/reply", json={"body": "nope"}
        )
        assert response.status_code == 401

    async def test_the_operator_sees_whether_agent_access_is_configured(
        self, user_a_client, as_admin, monkeypatch
    ):
        """So the console can say the queue is unreachable rather than
        letting somebody file requests nobody can collect."""
        monkeypatch.delenv("SUPPORT_AGENT_SECRET", raising=False)
        assert (await user_a_client.get("/api/v1/support")).json()["agent_access_configured"] is False

        monkeypatch.setenv("SUPPORT_AGENT_SECRET", SECRET)
        assert (await user_a_client.get("/api/v1/support")).json()["agent_access_configured"] is True


class TestFilteringAndCounts:
    async def test_active_filter_excludes_finished_requests(self, user_a_client, as_admin):
        first = await _raise(user_a_client, title="One")
        await _raise(user_a_client, title="Two")
        await user_a_client.post(
            f"/api/v1/support/{first['id']}/status", json={"status": "closed"}
        )

        body = (await user_a_client.get("/api/v1/support?status=active")).json()

        assert body["total"] == 1
        assert body["items"][0]["title"] == "Two"
        assert body["open_count"] == 1

    async def test_an_invalid_status_is_refused(self, user_a_client, as_admin):
        ticket = await _raise(user_a_client)
        response = await user_a_client.post(
            f"/api/v1/support/{ticket['id']}/status", json={"status": "banana"}
        )
        assert response.status_code == 400


class TestRoutingBetweenTheTwoAgents:
    """Only one agent may work a request.

    Two triage agents share this queue: the laptop every fifteen minutes, the
    cloud every hour. With no coordination both pick up the same request and
    both reply, which leaves an operator holding two diagnoses on one thread
    and no way to tell which to believe. The heartbeat is how the cloud run
    knows to stand down.
    """

    async def test_no_heartbeat_reads_as_the_laptop_being_absent(
        self, anon_client, agent_secret
    ):
        """The cloud must work the queue when nothing else is."""
        body = (await anon_client.get(
            "/api/v1/support/agent/queue", headers={"X-Support-Secret": SECRET}
        )).json()

        assert body["local_agent_active"] is False
        # Reported separately from the boolean: "never checked in" and
        # "checked in two hours ago" are different situations.
        assert body["local_agent_seconds_ago"] is None

    async def test_a_fresh_heartbeat_tells_the_cloud_to_stand_down(
        self, anon_client, agent_secret
    ):
        await anon_client.post(
            "/api/v1/support/agent/heartbeat",
            json={"agent": "local", "detail": "vishnus-macbook"},
            headers={"X-Support-Secret": SECRET},
        )

        body = (await anon_client.get(
            "/api/v1/support/agent/queue", headers={"X-Support-Secret": SECRET}
        )).json()

        assert body["local_agent_active"] is True
        assert body["local_agent_seconds_ago"] < 60

    async def test_a_stale_heartbeat_hands_the_queue_back(
        self, anon_client, db_session, agent_secret
    ):
        """A laptop shut two hours ago is not on the case."""
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select
        from models.agent_heartbeats import Agent_heartbeats

        await anon_client.post(
            "/api/v1/support/agent/heartbeat", json={"agent": "local"},
            headers={"X-Support-Secret": SECRET},
        )

        row = (await db_session.execute(select(Agent_heartbeats))).scalars().one()
        row.last_seen = datetime.now(timezone.utc) - timedelta(hours=2)
        await db_session.commit()

        body = (await anon_client.get(
            "/api/v1/support/agent/queue", headers={"X-Support-Secret": SECRET}
        )).json()

        assert body["local_agent_active"] is False
        assert body["local_agent_seconds_ago"] > 3600

    async def test_the_heartbeat_is_one_row_per_agent(self, anon_client, db_session, agent_secret):
        """Overwritten, not appended. A row per beat is 96 a day of noise."""
        from sqlalchemy import select
        from models.agent_heartbeats import Agent_heartbeats

        for _ in range(3):
            await anon_client.post(
                "/api/v1/support/agent/heartbeat", json={"agent": "local"},
                headers={"X-Support-Secret": SECRET},
            )

        rows = (await db_session.execute(select(Agent_heartbeats))).scalars().all()
        assert len(rows) == 1

    async def test_the_heartbeat_needs_the_secret(self, anon_client, agent_secret):
        response = await anon_client.post(
            "/api/v1/support/agent/heartbeat", json={"agent": "local"}
        )
        assert response.status_code == 401


class TestDeleting:
    async def test_an_admin_can_delete_a_request_and_its_thread(
        self, user_a_client, as_admin, db_session
    ):
        from sqlalchemy import select
        from models.support_tickets import Support_messages, Support_tickets

        ticket = await _raise(user_a_client)
        await user_a_client.post(
            f"/api/v1/support/{ticket['id']}/messages", json={"body": "detail"}
        )

        response = await user_a_client.request("DELETE", f"/api/v1/support/{ticket['id']}")

        assert response.status_code == 200
        assert (await db_session.execute(select(Support_tickets))).scalars().all() == []
        # The thread goes with it — orphaned messages pointing at a request
        # that no longer exists are just rows nobody can read.
        assert (await db_session.execute(select(Support_messages))).scalars().all() == []

    async def test_a_non_admin_cannot_delete(self, user_a_client, as_admin, monkeypatch):
        ticket = await _raise(user_a_client)
        monkeypatch.delenv("ADMIN_EMAILS", raising=False)

        response = await user_a_client.request("DELETE", f"/api/v1/support/{ticket['id']}")
        assert response.status_code == 403

    async def test_the_agent_can_delete_with_the_secret(
        self, user_a_client, anon_client, as_admin, agent_secret
    ):
        ticket = await _raise(user_a_client)

        response = await anon_client.request(
            "DELETE", f"/api/v1/support/agent/{ticket['id']}",
            headers={"X-Support-Secret": SECRET},
        )
        assert response.status_code == 200

    async def test_the_agent_cannot_delete_without_it(
        self, user_a_client, anon_client, as_admin, agent_secret
    ):
        ticket = await _raise(user_a_client)
        response = await anon_client.request("DELETE", f"/api/v1/support/agent/{ticket['id']}")
        assert response.status_code == 401

    async def test_the_deletion_is_recorded_before_the_rows_go(
        self, user_a_client, as_admin, db_session
    ):
        """So the fact a request existed survives the request itself."""
        import json
        from sqlalchemy import select
        from models.activity_events import Activity_events

        ticket = await _raise(user_a_client, title="Something worth remembering")
        await user_a_client.request("DELETE", f"/api/v1/support/{ticket['id']}")

        rows = (
            await db_session.execute(
                select(Activity_events).where(Activity_events.action == "support.deleted")
            )
        ).scalars().all()

        assert len(rows) == 1
        assert json.loads(rows[0].metadata_json)["title"] == "Something worth remembering"

    async def test_agent_all_lists_every_status(
        self, user_a_client, anon_client, as_admin, agent_secret
    ):
        """The queue shows only open work; a cleanup needs to see everything."""
        first = await _raise(user_a_client, title="One")
        await _raise(user_a_client, title="Two")
        await user_a_client.post(
            f"/api/v1/support/{first['id']}/status", json={"status": "resolved"}
        )

        body = (await anon_client.get(
            "/api/v1/support/agent/all", headers={"X-Support-Secret": SECRET}
        )).json()

        assert body["count"] == 2
        assert {i["title"] for i in body["items"]} == {"One", "Two"}
