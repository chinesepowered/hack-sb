from typing import Any

import httpx

BAND_BASE = "https://api.band.ai/api/v1"


class BandError(RuntimeError):
    def __init__(self, what: str, response: httpx.Response):
        self.status_code = response.status_code
        try:
            self.code = response.json().get("error", {}).get("code")
        except ValueError:
            self.code = None
        super().__init__(f"{what}: HTTP {response.status_code} {response.text[:300]}")


def mention(participant_id: str, name: str) -> dict[str, str]:
    return {"id": participant_id, "name": name}


def message_body(content: str, mentions: list[dict[str, str]]) -> dict[str, Any]:
    if not mentions:
        raise ValueError("Band text messages need at least one mention")
    return {"message": {"content": content, "mentions": mentions}}


class _Base:
    def __init__(self, api_key: str, http: httpx.AsyncClient | None = None):
        self._headers = {"X-API-Key": api_key}
        self._http = http or httpx.AsyncClient(timeout=30)

    async def _req(self, what: str, method: str, path: str, **kw: Any) -> httpx.Response:
        r = await self._http.request(method, f"{BAND_BASE}{path}", headers=self._headers, **kw)
        if r.status_code >= 400:
            raise BandError(what, r)
        return r


class BandUser(_Base):
    """Human API, authenticated with the user's key."""

    async def profile(self) -> dict[str, Any]:
        return (await self._req("profile", "GET", "/me/profile")).json()["data"]

    async def register_agent(self, name: str, description: str) -> tuple[str, str]:
        r = await self._req(
            f"register {name}",
            "POST",
            "/me/agents/register",
            json={"agent": {"name": name, "description": description}},
        )
        data = r.json()["data"]
        return data["agent"]["id"], data["credentials"]["api_key"]

    async def create_room(self, title: str, participant_ids: list[str]) -> str:
        r = await self._req(
            "create room",
            "POST",
            "/me/chats",
            json={"chat": {"title": title, "participants": [{"participant_id": p} for p in participant_ids]}},
        )
        return r.json()["data"]["id"]

    async def send(self, chat_id: str, content: str, mentions: list[dict[str, str]]) -> str:
        r = await self._req("send", "POST", f"/me/chats/{chat_id}/messages", json=message_body(content, mentions))
        return r.json()["data"]["id"]

    async def messages_after(self, chat_id: str, after_id: str | None, limit: int = 50) -> list[dict[str, Any]]:
        """Oldest-first messages newer than after_id; with no anchor, the latest page in chronological order."""
        params: dict[str, Any] = {"limit": limit, "message_types": "text"}
        if after_id:
            params["after"] = after_id
        r = await self._req("list messages", "GET", f"/me/chats/{chat_id}/messages", params=params)
        msgs = r.json()["data"]
        return msgs if after_id else list(reversed(msgs))


class BandAgent(_Base):
    """Agent API, authenticated with one agent's key."""

    async def next_message(self, chat_id: str) -> dict[str, Any] | None:
        r = await self._req("next", "GET", f"/agent/chats/{chat_id}/messages/next")
        if r.status_code == 204 or not r.content:
            return None
        return r.json()["data"]

    async def mark(self, chat_id: str, message_id: str, status: str) -> None:
        await self._req(f"mark {status}", "POST", f"/agent/chats/{chat_id}/messages/{message_id}/{status}")

    async def send(self, chat_id: str, content: str, mentions: list[dict[str, str]]) -> str:
        r = await self._req("send", "POST", f"/agent/chats/{chat_id}/messages", json=message_body(content, mentions))
        return r.json()["data"]["id"]

    async def create_task(self, chat_id: str, subject: str, detail: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"subject": subject}
        if detail:
            body["detail"] = detail
        return (await self._req("create task", "POST", f"/agent/chats/{chat_id}/tasks", json=body)).json()["data"]

    async def set_goal(self, chat_id: str, title: str, summary: str | None = None) -> None:
        body = {"goal_title": title}
        if summary:
            body["goal_summary"] = summary
        await self._req("set goal", "PUT", f"/agent/chats/{chat_id}/board", json=body)
