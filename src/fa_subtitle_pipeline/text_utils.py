"""Text helpers: Persian normalisation, wrapping and readability checks."""
from __future__ import annotations

import re

from .srt_io import SubtitleEntry

_TAG_RE = re.compile(r"<[^>]+>")
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

# Arabic presentation characters that often sneak in from translators/OCR.
_NORMALISE = str.maketrans({
    "ي": "ی",  # Arabic Yeh -> Persian Yeh
    "ك": "ک",  # Arabic Kaf -> Persian Kaf
    "ة": "ه",
    "ؤ": "و",
    "إ": "ا",
    "أ": "ا",
    "ٱ": "ا",
})


def strip_tags(text: str) -> str:
    return _TAG_RE.sub("", text)


def normalize_persian(text: str) -> str:
    """Normalise mixed Arabic/Persian glyphs and whitespace for clean rendering."""
    text = strip_tags(text).translate(_NORMALISE)
    text = text.replace("\r", "")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def to_persian_digits(text: str) -> str:
    return text.translate(_FA_DIGITS)


def wrap_text(text: str, max_chars_per_line: int = 40, max_lines: int = 2) -> str:
    """Greedy word-wrap. Explicit newlines in the source are respected first."""
    out_lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            continue
        line = words[0]
        for word in words[1:]:
            if len(line) + 1 + len(word) <= max_chars_per_line:
                line += " " + word
            else:
                out_lines.append(line)
                line = word
        out_lines.append(line)
    if len(out_lines) > max_lines:
        # Keep at most max_lines by merging the overflow into the last line.
        out_lines = out_lines[: max_lines - 1] + [" ".join(out_lines[max_lines - 1:])]
    return "\n".join(out_lines)


def chars_per_second(entry: SubtitleEntry) -> float:
    if entry.duration <= 0:
        return float("inf")
    return len(entry.text.replace("\n", " ")) / entry.duration


def quality_warnings(
    entries: list[SubtitleEntry], max_cps: float = 22.0, max_chars: int = 90
) -> list[str]:
    """Readability warnings: subtitles that are too long/fast to read."""
    warnings: list[str] = []
    for e in entries:
        cps = chars_per_second(e)
        n_chars = len(e.text.replace("\n", " "))
        if cps > max_cps:
            warnings.append(
                f"#{e.index} ({e.start:.1f}s): {cps:.0f} نویسه/ثانیه — برای خواندن سریع است: {e.text!r}"
            )
        elif n_chars > max_chars:
            warnings.append(
                f"#{e.index} ({e.start:.1f}s): {n_chars} نویسه — جمله طولانی است: {e.text!r}"
            )
    return warnings


def similarity_ratio(a: list[SubtitleEntry], b: list[SubtitleEntry]) -> float:
    """Fraction of entries whose text is identical (used to detect an
    un-translated manual template)."""
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    same = sum(1 for i in range(n) if a[i].text.strip() == b[i].text.strip())
    return same / n
