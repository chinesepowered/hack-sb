import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .band import BandAgent, BandUser, mention
from .config import HELPERS, PERSONAS, Setup
from .lyzr import LyzrClient

log = logging.getLogger("capy.pod")

LEADING_MENTIONS = re.compile(r"^\s*(?:@\S+[\s,:]*)+")
_NEGATIVE = re.compile(r"\b(no|nope|not|don'?t|change|instead|but|less|more)\b", re.I)
_POSITIVE = re.compile(
    r"\b(yes|yep|yeah|yup|ok|okay|sure|perfect|approve[d]?|sounds good|looks good|love it|do it|let'?s go)\b|👍|💛|❤️",
    re.I,
)


def strip_mentions(text: str) -> str:
    return LEADING_MENTIONS.sub("", text or "").strip()


def is_approval(text: str) -> bool:
    return bool(_POSITIVE.search(text)) and not _NEGATIVE.search(text)


def checklist_items(text: str) -> list[str]:
    items = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*)$", line)
        if m and m.group(1).strip():
            items.append(m.group(1).strip().rstrip("."))
    return items[:5]


class Bus:
    """Fan-out of UI events to every connected SSE client."""

    def __init__(self) -> None:
        self._subs: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subs.discard(q)

    def publish(self, event: dict[str, Any]) -> None:
        for q in self._subs:
            q.put_nowait(event)


@dataclass
class RoomState:
    phase: str = "idle"  # idle -> gathering -> awaiting_approval -> approved -> done
    worry: str = ""
    notes: dict[str, str] = field(default_factory=dict)
    plan: str = ""
    tasks: list[str] = field(default_factory=list)


class Pod:
    def __init__(self, setup: Setup, lyzr: LyzrClient, bus: Bus):
        self.setup = setup
        self.lyzr = lyzr
        self.bus = bus
        self.state = RoomState()
        self.agents = {k: BandAgent(c.band_api_key) for k, c in setup.capys.items()}
        self.by_band_id = {c.band_agent_id: k for k, c in setup.capys.items()}
        self._seen: dict[str, set[str]] = {k: set() for k in setup.capys}

    # ---- helpers -------------------------------------------------------
    def m(self, key: str) -> dict[str, str]:
        return mention(self.setup.capys[key].band_agent_id, PERSONAS[key].name)

    def human(self) -> dict[str, str]:
        return mention(self.setup.human_id, self.setup.human_name)

    def set_phase(self, phase: str) -> None:
        self.state.phase = phase
        self.bus.publish({"type": "phase", "phase": phase})

    async def think(self, key: str, prompt: str) -> str:
        self.bus.publish({"type": "thinking", "capy": key, "on": True})
        try:
            return await self.lyzr.chat(
                self.setup.capys[key].lyzr_agent_id, f"{self.setup.room_id}-{key}", prompt
            )
        finally:
            self.bus.publish({"type": "thinking", "capy": key, "on": False})

    async def say(self, key: str, text: str, to: list[dict[str, str]]) -> None:
        await self.agents[key].send(self.setup.room_id, text, to)

    def reset(self, room_id: str) -> None:
        self.setup.room_id = room_id
        self.state = RoomState()
        self.bus.publish({"type": "phase", "phase": "idle"})

    # ---- run loops -----------------------------------------------------
    async def run(self) -> None:
        await asyncio.gather(*(self._loop(k) for k in self.setup.capys))

    async def _loop(self, key: str) -> None:
        agent = self.agents[key]
        while True:
            room = self.setup.room_id
            try:
                msg = await agent.next_message(room)
            except Exception as e:  # network blips shouldn't kill the capy
                log.warning("%s poll failed: %s", key, e)
                await asyncio.sleep(3)
                continue
            if msg is None:
                await asyncio.sleep(0.8)
                continue
            mid = msg["id"]
            await agent.mark(room, mid, "processing")
            if mid in self._seen[key] or msg["sender_id"] == self.setup.capys[key].band_agent_id:
                await agent.mark(room, mid, "processed")
                continue
            self._seen[key].add(mid)
            try:
                await self.handle(key, msg)
                await agent.mark(room, mid, "processed")
            except Exception:
                log.exception("%s failed on message %s", key, mid)
                await agent.mark(room, mid, "failed")

    # ---- the brains ----------------------------------------------------
    async def handle(self, key: str, msg: dict[str, Any]) -> None:
        text = strip_mentions(msg.get("content", ""))
        sender = self.by_band_id.get(msg["sender_id"], "human" if msg.get("sender_type") == "User" else "other")
        log.info("%s <- %s: %s", key, sender, text[:80])
        if key == "yuzu":
            await self._yuzu(sender, text)
        else:
            await self._helper(key, sender, text)

    async def _yuzu(self, sender: str, text: str) -> None:
        s = self.state
        if sender == "human":
            if s.phase == "awaiting_approval" and is_approval(text):
                self.set_phase("approved")
                await self.say(
                    "yuzu",
                    "Yay, the guest said yes! 🍊 Mochi, could you tuck this onto our task board?",
                    [self.m("mochi")],
                )
                return
            if s.phase == "awaiting_approval":
                s.plan = await self.think(
                    "yuzu", f"REVISE mode.\nCurrent plan:\n{s.plan}\n\nGuest feedback: {text}"
                )
                await self.say("yuzu", s.plan, [self.human()])
                return
            self.state = s = RoomState(worry=text)
            self.set_phase("gathering")
            welcome = await self.think("yuzu", f"WELCOME mode.\nGuest's worry: {text}")
            await self.say("yuzu", welcome, [self.m(h) for h in HELPERS])
            return

        if sender in HELPERS and s.phase == "gathering":
            s.notes[sender] = text
            self.bus.publish({"type": "progress", "notes": len(s.notes), "of": len(HELPERS)})
            if len(s.notes) < len(HELPERS):
                return
            notes = "\n".join(f"{PERSONAS[h].name}: {s.notes[h]}" for h in HELPERS)
            s.plan = await self.think("yuzu", f"PLAN mode.\nGuest's worry: {s.worry}\n\nNotes:\n{notes}")
            self.set_phase("awaiting_approval")
            await self.say("yuzu", s.plan, [self.human()])

    async def _helper(self, key: str, sender: str, text: str) -> None:
        s = self.state
        if key == "mochi" and s.phase == "approved":
            checklist = await self.think("mochi", f"CHECKLIST for this plan:\n{s.plan}")
            items = checklist_items(checklist) or checklist_items(s.plan)
            room = self.setup.room_id
            await self.agents["mochi"].set_goal(room, "Soak away the stress ♨️", s.worry[:300])
            for item in items:
                await self.agents["mochi"].create_task(room, item)
            s.tasks = items
            self.bus.publish({"type": "tasks", "items": items})
            lines = "\n".join(f"☐ {i}" for i in items)
            await self.say(
                "mochi",
                f"All tucked onto the task board 🗓️\n{lines}\nOne little step at a time. You've got this.",
                [self.human()],
            )
            self.set_phase("done")
            return
        if sender == "yuzu" and s.worry:
            note = await self.think(key, f"The guest's worry: {s.worry}\n\nYuzu asks the pod for help. Your note:")
            await self.say(key, note, [self.m("yuzu")])
