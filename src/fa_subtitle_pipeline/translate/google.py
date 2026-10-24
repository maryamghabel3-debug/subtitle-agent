"""Free Google Translate provider (optional dependency: deep-translator)."""
from __future__ import annotations

from ..srt_io import SubtitleEntry
from .base import TranslationProvider, _with_texts


class GoogleProvider(TranslationProvider):
    name = "google"

    def translate(self, entries: list[SubtitleEntry]) -> list[SubtitleEntry]:
        try:
            from deep_translator import GoogleTranslator
        except ImportError as exc:
            raise RuntimeError(
                "deep-translator نصب نیست. اجرا کنید:\n"
                '  pip install ".[google]"'
            ) from exc
        translator = GoogleTranslator(
            source=self.cfg.source_language, target=self.cfg.target_language
        )
        print(f"🌐 ترجمه با گوگل ({len(entries)} خط) ...")
        texts: list[str] = []
        for i, e in enumerate(entries, 1):
            source = e.text.replace("\n", " ")
            try:
                texts.append(translator.translate(source) or source)
            except Exception as exc:  # keep going; review step will catch it
                print(f"⚠️  خط {i} ترجمه نشد ({exc})؛ متن اصلی نگه داشته شد.")
                texts.append(source)
        return _with_texts(entries, texts)
