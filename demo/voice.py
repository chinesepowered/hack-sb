"""Generate the demo voiceover with ElevenLabs (Jessica)."""

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE.parent / ".env")

JESSICA = "cgSgspJ2msm6clMCkdW9"

SCRIPT = (
    "Hi! This is Capy Onsen. When life piles up, an exam on Friday, moving on Saturday, "
    "your mom's birthday on Sunday, most chatbots hand you a wall of text. "
    "So we built a hot spring instead. "
    "Meet the pod. Yuzu is the host, with a little yuzu on her head. "
    "Momo finds what really matters. Mochi plans the steps. And Pebble makes sure you actually rest. "
    "Each capybara is its own Lyzr agent, with its own role and memory. "
    "And they all live in a real Band room. "
    "Watch. I drop my worry in the water and mention Yuzu. "
    "Yuzu welcomes me, then at-mentions Momo, Mochi and Pebble. "
    "Band routes the message only to them, and all three think in parallel on Lyzr. "
    "They each reply back to Yuzu, and she merges their notes into one gentle plan. "
    "Then she asks me: does this feel okay? That's the human in the loop. "
    "I say yes. Yuzu hands off to Mochi, who sets the room goal and puts every step "
    "onto Band's task board. Real tasks, not just a chat bubble. "
    "And the stress meter? All the way down. "
    "Under the hood: four Band agents using the Agent API message loop and at-mention routing, "
    "four Lyzr agents with a session per room, and a tiny FastAPI server mirroring the Band room live. "
    "Capy Onsen. Bring your stress to the hot spring, and leave with a plan. Thanks for watching!"
)


def main() -> None:
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{JESSICA}",
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
        json={
            "text": SCRIPT,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35},
        },
        timeout=180,
    )
    if r.status_code >= 400:
        raise SystemExit(f"ElevenLabs HTTP {r.status_code}: {r.text[:300]}")
    (out / "voiceover.mp3").write_bytes(r.content)
    print("wrote", out / "voiceover.mp3")


if __name__ == "__main__":
    main()
