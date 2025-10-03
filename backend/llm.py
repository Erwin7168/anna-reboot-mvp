# backend/llm.py
import os
from pathlib import Path
from openai import OpenAI

def load_system_prompt() -> str:
    # 1) Environment variables (handig als je de prompt niet in GitHub wilt)
    for key in ("SYSTEM_PROMPT", "ANNA_SYSTEM_PROMPT", "ANNA_SYSTEM_TEXT"):
        val = os.getenv(key)
        if val and val.strip():
            return val
    # 2) Fallback: bestand in repo
    prompt_path = Path(__file__).resolve().parent / "prompts" / "anna_system_nl.md"
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"System prompt niet gevonden op {prompt_path}. "
            "Maak dit bestand aan of zet SYSTEM_PROMPT als environment variable."
        )
    return prompt_path.read_text(encoding="utf-8")

SYSTEM_PROMPT = load_system_prompt()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def chat_anna(history, user_message, model: str = "gpt-4o-mini", temperature: float = 0.5) -> str:
    """
    history: [{"role":"user"|"assistant","content":"..."}]
    user_message: laatste user tekst (string)
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if isinstance(history, list):
        for m in history:
            r = m.get("role")
            if r in ("user", "assistant"):
                messages.append({"role": r, "content": str(m.get("content", ""))})
    messages.append({"role": "user", "content": str(user_message)})

    resp = client.chat.completions.create(
        model=model,          # "gpt-4o" kan ook; "gpt-4o-mini" is goedkoper
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content
