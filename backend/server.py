import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from capy.band import BandUser, mention
from capy.config import PERSONAS, WEB_DIST, Setup, env
from capy.lyzr import LyzrClient
from capy.pod import Bus, Pod, strip_mentions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("capy.server")

setup = Setup.load()
bus = Bus()
user = BandUser(env("BAND_USER_API_KEY"))
pod = Pod(setup, LyzrClient(env("LYZR_API_KEY"), user_id="capy-onsen"), bus)
history: list[dict[str, Any]] = []


def to_event(msg: dict[str, Any]) -> dict[str, Any]:
    who = pod.by_band_id.get(msg["sender_id"], "you" if msg["sender_type"] == "User" else "other")
    return {
        "type": "message",
        "id": msg["id"],
        "from": who,
        "text": strip_mentions(msg["content"]),
        "at": msg.get("inserted_at"),
    }


async def mirror_room() -> None:
    """Poll the real Band room with the user's key so the onsen shows exactly what Band has."""
    last_id: str | None = None
    room = setup.room_id
    while True:
        try:
            if room != setup.room_id:
                room, last_id = setup.room_id, None
                history.clear()
            msgs = await user.messages_after(room, last_id)
            for msg in msgs:
                ev = to_event(msg)
                history.append(ev)
                bus.publish(ev)
            if msgs:
                last_id = msgs[-1]["id"]
        except Exception as e:
            log.warning("mirror failed: %s", e)
            await asyncio.sleep(2)
        await asyncio.sleep(0.7)


@asynccontextmanager
async def lifespan(_: FastAPI):
    tasks = [asyncio.create_task(pod.run()), asyncio.create_task(mirror_room())]
    log.info("Capy Onsen open. Band room %s", setup.room_id)
    yield
    for t in tasks:
        t.cancel()
        with suppress(asyncio.CancelledError):
            await t


app = FastAPI(lifespan=lifespan)


@app.get("/api/state")
async def state() -> dict[str, Any]:
    return {
        "room_id": setup.room_id,
        "phase": pod.state.phase,
        "tasks": pod.state.tasks,
        "capys": {k: {"name": p.name, "role": p.role} for k, p in PERSONAS.items()},
        "human": setup.human_name,
    }


@app.get("/api/stream")
async def stream():
    q = bus.subscribe()

    async def events():
        try:
            yield {"data": json.dumps({"type": "hello", "phase": pod.state.phase, "history": history, "tasks": pod.state.tasks})}
            while True:
                yield {"data": json.dumps(await q.get())}
        finally:
            bus.unsubscribe(q)

    return EventSourceResponse(events(), ping=15)


class Say(BaseModel):
    text: str


@app.post("/api/say")
async def say(body: Say) -> dict[str, str]:
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Say something to the capys 🫧")
    yuzu = setup.capys["yuzu"].band_agent_id
    msg_id = await user.send(setup.room_id, text, [mention(yuzu, "Yuzu")])
    return {"id": msg_id}


@app.post("/api/reset")
async def reset() -> dict[str, str]:
    room = await user.create_room("Capy Onsen ♨️", [c.band_agent_id for c in setup.capys.values()])
    pod.reset(room)
    setup.save()
    bus.publish({"type": "reset", "room_id": room})
    return {"room_id": room}


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
