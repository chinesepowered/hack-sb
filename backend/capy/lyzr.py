from typing import Any

import httpx

LYZR_BASE = "https://agent-prod.studio.lyzr.ai"


class LyzrError(RuntimeError):
    pass


def extract_reply(payload: Any) -> str:
    """Lyzr's chat response shape isn't documented; accept the shapes seen in practice."""
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        for key in ("response", "message", "content", "output", "text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested = extract_reply(value)
                if nested:
                    return nested
        data = payload.get("data")
        if data is not None:
            return extract_reply(data)
    return ""


class LyzrClient:
    def __init__(self, api_key: str, user_id: str, http: httpx.AsyncClient | None = None):
        self._headers = {"x-api-key": api_key, "Content-Type": "application/json"}
        self._user_id = user_id
        self._http = http or httpx.AsyncClient(timeout=90)

    async def create_agent(self, *, name: str, role: str, goal: str, instructions: str) -> str:
        body = {
            "name": name,
            "description": goal,
            "agent_role": role,
            "agent_goal": goal,
            "agent_instructions": instructions,
            "provider_id": "OpenAI",
            "model": "gpt-4o-mini",
            "llm_credential_id": "lyzr_openai",
            "temperature": 0.7,
            "top_p": 0.9,
            "features": [],
            "tools": [],
        }
        r = await self._http.post(f"{LYZR_BASE}/v3/agents/", headers=self._headers, json=body)
        if r.status_code >= 400:
            raise LyzrError(f"create agent {name}: HTTP {r.status_code} {r.text[:300]}")
        data = r.json()
        agent_id = data.get("agent_id") or data.get("_id") or data.get("id")
        if not agent_id:
            raise LyzrError(f"create agent {name}: no id in {data}")
        return agent_id

    async def chat(self, agent_id: str, session_id: str, message: str) -> str:
        body = {
            "user_id": self._user_id,
            "agent_id": agent_id,
            "session_id": session_id,
            "message": message,
        }
        r = await self._http.post(f"{LYZR_BASE}/v3/inference/chat/", headers=self._headers, json=body)
        if r.status_code >= 400:
            raise LyzrError(f"chat {agent_id}: HTTP {r.status_code} {r.text[:300]}")
        reply = extract_reply(r.json())
        if not reply:
            raise LyzrError(f"chat {agent_id}: empty reply {r.text[:300]}")
        return reply
