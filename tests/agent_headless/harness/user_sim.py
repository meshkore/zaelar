#
# Synthetic USER simulator — a person talking to the zaelar personal assistant (English, text-level).
#
# Mirror image of the interview prototype's synthetic *candidate* (prototype_candidate/candidate.py), but here
# the bot plays the PERSON seeking assistance: greeting, probing what the assistant can do, giving tasks,
# referring back to earlier things to test memory, throwing curveballs. Voice is already solved, so this runs at
# the reasoning/text level to iterate on logic and prompts fast and cheap.
#
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ZAELAR = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


def _call(messages, model, temperature, max_tokens):
    import sys
    if ZAELAR not in sys.path:
        sys.path.insert(0, ZAELAR)
    from voice import llm
    return llm.call_llm(messages, model=model, temperature=temperature, max_tokens=max_tokens)


class UserSim:
    """LLM-driven person using the assistant. Keeps its OWN view of the dialogue (user = the assistant's words)."""

    def __init__(self, persona: str = "busy_pro", model: str = "gpt-4.1"):
        self.model = model
        self.persona = persona
        path = os.path.join(HERE, "personas", f"{persona}.md")
        persona_txt = open(path, encoding="utf-8").read() if os.path.exists(path) else f"You are a person named {persona}."
        sys = (persona_txt + "\n\n## How to behave in this simulation\n"
               "You are the HUMAN talking to a voice assistant. Output ONLY what you'd say out loud — no stage "
               "directions, no quotes, no narration. Natural spoken English. Vary your length like a real person; "
               "don't reuse the same opener or filler every turn. Stay in character. You are NOT the assistant; "
               "never answer your own questions or play both sides.\n"
               "Pursue your own goals from the persona. When you're genuinely satisfied (or done testing), wrap up "
               "naturally and end your message with the token <END> on its own. Don't drag it out past what a real "
               "person would; aim for a realistic short session.")
        self.history = [{"role": "system", "content": sys}]
        self.turns = 0

    def hears(self, assistant_text: str):
        self.history.append({"role": "user", "content": assistant_text})

    def say(self) -> str:
        self.turns += 1
        # First turn slightly longer is fine (an opener); afterwards keep it spoken-length.
        hint = ("This is your opening line to the assistant — react to its greeting and start pursuing what you "
                "came for." if self.turns == 1 else
                "Keep it spoken-length (usually one or two sentences). Push your own agenda; react to what it just said.")
        msgs = self.history + [{"role": "system", "content": hint}]
        txt = (_call(msgs, self.model, temperature=0.9, max_tokens=160) or "").strip()
        self.history.append({"role": "assistant", "content": txt})
        return txt
