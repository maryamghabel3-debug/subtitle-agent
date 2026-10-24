"""LLM translation via any OpenAI-compatible Chat Completions API.

Works with OpenAI, OpenRouter, Groq, a local LM Studio server, etc. — just
change `translation_api_base` / `translation_model` and set the API key in
the environment variable named by `translation_api_key_env`.
Implemented with urllib only, so no extra dependency is required later when
you get an API key: it simply starts working.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

from ..srt_io import SubtitleEntry
from .base import TranslationProvider, _with_texts

_SYSTEM_PROMPT = """You are a professional subtitle translator.
Translate each numbered subtitle line into Persian (Farsi).
Rules:
- Return ONLY a JSON array of strings, exactly one string per input line, in order.
- Keep translations SHORT and readable as subtitles (a viewer has ~2 seconds per line).
- Natural spoken Persian, faithful to meaning and tone; keep names in a natural form.
- Do not merge or split lines. Do not add numbering or explanations.
Style: {style}"""


def parse_batch_response(content: str, expected: int) -> list[str]:
    """Parse the model reply: JSON array (preferred) or numbered lines."""
    content = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if fenced:
        content = fenced.group(1).strip()
    try:
        data = json.loads(content)
        if isinstance(data, list) and len(data) == expected:
            return [str(x) for x in data]
    except json.JSONDecodeError:
        pass
    lines = []
    for raw in content.splitlines():
        m = re.match(r"\s*\d+\s*[.):\-]\s*(.*)", raw)
        if m:
            lines.append(m.group(1).strip())
    if len(lines) == expected:
        return lines
    raise ValueError(
        f"Could not parse {expected} translations from model response: {content[:300]}..."
    )


class OpenAIProvider(TranslationProvider):
    name = "openai"

    def _call_api(self, user_prompt: str) -> str:
        api_key = [SECURITY_DATA]
        if not api_key:
            raise RuntimeError(
                f"کلید API پیدا نشد! متغیر محیطی {self.cfg.translation_api_key_env} را تنظیم کنید، "
                "مثلاً:\n"
                f"  export {self.cfg.translation_api_key_env}=sk-...      (لینوکس/مک)\n"
                f"  $env:{self.cfg.translation_api_key_env}='sk-...'     (PowerShell)"
            )
        payload = json.dumps({
            "model": self.cfg.translation_model,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT.format(style=self.cfg.translation_style)},
                {"role": "user", "content": user_prompt},
            ],
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.cfg.translation_api_base.rstrip('/')}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    def translate(self, entries: list[SubtitleEntry]) -> list[SubtitleEntry]:
        batch = max(1, self.cfg.translation_batch_size)
        texts: list[str] = []
        total = (len(entries) + batch - 1) // batch
        for b in range(total):
            chunk = entries[b * batch:(b + 1) * batch]
            numbered = "\n".join(
                f"{i + 1}. {e.text.replace(chr(10), ' ')}" for i, e in enumerate(chunk)
            )
            print(f"🤖 ترجمه دسته {b + 1}/{total} با {self.cfg.translation_model} ...")
            texts.extend(parse_batch_response(self._call_api(numbered), len(chunk)))
        return _with_texts(entries, texts)
