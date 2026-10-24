"""Translation provider interface."""
from __future__ import annotations

from ..config import PipelineConfig
from ..srt_io import SubtitleEntry


class TranslationProvider:
    name = "base"

    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg

    def translate(self, entries: list[SubtitleEntry]) -> list[SubtitleEntry]:
        raise NotImplementedError


def _with_texts(entries: list[SubtitleEntry], texts: list[str]) -> list[SubtitleEntry]:
    if len(texts) != len(entries):
        raise ValueError(
            f"Translation returned {len(texts)} lines for {len(entries)} subtitles"
        )
    from dataclasses import replace

    from ..text_utils import normalize_persian

    return [
        replace(e, text=normalize_persian(t)) for e, t in zip(entries, texts)
    ]
