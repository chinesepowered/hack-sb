"""One-time setup: Lyzr agents + Band agents + a Band room for the capy pod. Safe to re-run."""

import asyncio
import json

from capy.band import BandError, BandUser
from capy.config import CAPYS_FILE, PERSONAS, env
from capy.lyzr import LyzrClient

ROOM_TITLE = "Capy Onsen ♨️"


def load_progress() -> dict:
    if CAPYS_FILE.exists():
        return json.loads(CAPYS_FILE.read_text())
    return {"capys": {}}


def save_progress(state: dict) -> None:
    CAPYS_FILE.write_text(json.dumps(state, indent=2))


async def main() -> None:
    state = load_progress()
    band = BandUser(env("BAND_USER_API_KEY"))
    lyzr = LyzrClient(env("LYZR_API_KEY"), user_id="capy-onsen")

    me = await band.profile()
    state["human_id"] = me["id"]
    state["human_name"] = me.get("first_name") or me["handle"]
    print(f"Band user: @{me['handle']}")

    for key, p in PERSONAS.items():
        capy = state["capys"].setdefault(key, {})
        if "lyzr_agent_id" not in capy:
            capy["lyzr_agent_id"] = await lyzr.create_agent(
                name=f"Capy {p.name}", role=p.role, goal=p.goal, instructions=p.instructions
            )
            save_progress(state)
        print(f"  Lyzr  {p.name:<7} {capy['lyzr_agent_id']}")

        if "band_agent_id" not in capy:
            try:
                capy["band_agent_id"], capy["band_api_key"] = await band.register_agent(p.name, p.band_description)
            except BandError as e:
                if e.code == "limit_reached":
                    raise SystemExit(
                        "Band says your plan's agent limit is reached. Delete an unused agent in the Band web app "
                        "(Agents page) and re-run this script; progress so far is saved."
                    ) from e
                raise
            save_progress(state)
        print(f"  Band  {p.name:<7} {capy['band_agent_id']}")

    if "room_id" not in state:
        state["room_id"] = await band.create_room(
            ROOM_TITLE, [c["band_agent_id"] for c in state["capys"].values()]
        )
        save_progress(state)
    print(f"Room: {state['room_id']}  (open https://app.band.ai to watch it)")
    print(f"Saved to {CAPYS_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
