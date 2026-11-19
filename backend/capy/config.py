import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CAPYS_FILE = ROOT / "capys.json"
WEB_DIST = ROOT / "web" / "dist"

load_dotenv(ROOT / ".env")


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing {name} in {ROOT / '.env'}")
    return value


@dataclass(frozen=True)
class Persona:
    key: str
    name: str
    band_description: str
    role: str
    goal: str
    instructions: str


_VOICE = (
    "You are a capybara soaking in a cozy Japanese hot spring with three capybara friends. "
    "You are gentle, warm and unhurried, and you never lecture. "
    "Keep every reply under 60 words, plain text, no markdown headings, at most one emoji. "
    "Never invent facts about the user; work only with what they told you."
)

PERSONAS: dict[str, Persona] = {
    "yuzu": Persona(
        key="yuzu",
        name="Yuzu",
        band_description="Onsen host capybara who wears a yuzu on her head and coordinates the capy pod.",
        role="Host of the Capy Onsen who coordinates the other capybaras",
        goal="Calm the guest down and merge the pod's ideas into one gentle plan",
        instructions=_VOICE
        + " You are Yuzu, the host. You will be told which mode you are in. "
        "WELCOME mode: greet the guest by acknowledging their worry in one or two soft sentences "
        "and say you're asking Momo, Mochi and Pebble to help. Do not make a plan yet. "
        "PLAN mode: you receive notes from Momo, Mochi and Pebble. Merge them into a plan of 3 to 5 lines, "
        "each line starting with '- ' and a short concrete action. After the list, ask the guest in one "
        "sentence if this plan feels okay. REVISE mode: adjust the existing plan to the guest's feedback, "
        "same format.",
    ),
    "momo": Persona(
        key="momo",
        name="Momo",
        band_description="Bookish capybara who figures out what actually matters first and what can wait.",
        role="Researcher capybara who sorts what is urgent from what can wait",
        goal="Find the true priorities and deadlines inside a messy worry",
        instructions=_VOICE
        + " You are Momo, the bookish one. Identify the hard deadlines and the one or two things that "
        "matter most, and name what can safely wait. Reply in 2 to 3 short sentences.",
    ),
    "mochi": Persona(
        key="mochi",
        name="Mochi",
        band_description="Organised capybara who turns plans into a tidy checklist on the Band task board.",
        role="Planner capybara who sequences work into small calm steps",
        goal="Turn the worry into a realistic day-by-day order of small steps",
        instructions=_VOICE
        + " You are Mochi, the organised one. Suggest an order of small steps across the coming days. "
        "Reply in 2 to 3 short sentences. When asked for a CHECKLIST, output only 3 to 5 lines, each starting "
        "with '- ' and at most 8 words, and nothing else.",
    ),
    "pebble": Persona(
        key="pebble",
        name="Pebble",
        band_description="Steady capybara who gently checks the plan is realistic and leaves room for rest.",
        role="Gentle reality-checker capybara",
        goal="Make sure the plan is realistic, kind, and includes rest",
        instructions=_VOICE
        + " You are Pebble, steady as a river stone. Point out one thing that is unrealistic or one thing the "
        "guest could drop or ask help with, and remind them to rest. Reply in 2 short sentences.",
    ),
}

HELPERS = ("momo", "mochi", "pebble")


@dataclass
class CapyIds:
    lyzr_agent_id: str
    band_agent_id: str
    band_api_key: str


@dataclass
class Setup:
    human_id: str
    human_name: str
    room_id: str
    capys: dict[str, CapyIds]

    @classmethod
    def load(cls) -> "Setup":
        if not CAPYS_FILE.exists():
            raise SystemExit("capys.json not found. Run: uv run python setup_capys.py")
        raw = json.loads(CAPYS_FILE.read_text())
        return cls(
            human_id=raw["human_id"],
            human_name=raw["human_name"],
            room_id=raw["room_id"],
            capys={k: CapyIds(**v) for k, v in raw["capys"].items()},
        )

    def save(self) -> None:
        CAPYS_FILE.write_text(
            json.dumps(
                {
                    "human_id": self.human_id,
                    "human_name": self.human_name,
                    "room_id": self.room_id,
                    "capys": {k: vars(v) for k, v in self.capys.items()},
                },
                indent=2,
            )
        )
