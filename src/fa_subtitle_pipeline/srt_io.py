"""Reading, writing and transforming SRT subtitle files.

Implemented with the standard library only so the core pipeline has almost
no mandatory dependencies.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

_TS_RE = re.compile(
    r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{1,3})"
    r"\s*-->\s*"
    r"(?P<h2>\d{1,2}):(?P<m2>\d{2}):(?P<s2>\d{2})[,.](?P<ms2>\d{1,3})"
)


@dataclass
class SubtitleEntry:
    index: int
    start: float  # seconds
    end: float    # seconds
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def _to_seconds(h: str, m: str, s: str, ms: str) -> float:
    ms = (ms + "000")[:3]
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def format_srt_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    ms_total = int(round(seconds * 1000))
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_ass_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    cs_total = int(round(seconds * 100))
    h, rem = divmod(cs_total, 360_000)
    m, rem = divmod(rem, 6_000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def parse_srt(content: str) -> list[SubtitleEntry]:
    """Parse SRT (and simple WebVTT) content into entries."""
    content = content.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if content.startswith("WEBVTT"):
        # Drop the header line; cue format below is compatible enough.
        content = content.split("\n", 1)[1] if "\n" in content else ""
    entries: list[SubtitleEntry] = []
    for block in re.split(r"\n\s*\n", content):
        lines = [ln for ln in block.strip("\n").split("\n")]
        if not any("-->" in ln for ln in lines):
            continue
        ts_pos = next(i for i, ln in enumerate(lines) if "-->" in ln)
        match = _TS_RE.search(lines[ts_pos])
        if not match:
            continue
        start = _to_seconds(match["h"], match["m"], match["s"], match["ms"])
        end = _to_seconds(match["h2"], match["m2"], match["s2"], match["ms2"])
        text = "\n".join(lines[ts_pos + 1:]).strip()
        if not text:
            continue
        # Index is the numeric line before the timestamps, if present.
        index = len(entries) + 1
        if ts_pos > 0 and lines[0].strip().isdigit():
            index = int(lines[0].strip())
        entries.append(SubtitleEntry(index=index, start=start, end=end, text=text))
    entries.sort(key=lambda e: (e.start, e.end))
    return reindex(entries)


def read_srt(path: str | Path) -> list[SubtitleEntry]:
    """Read an SRT file, tolerating the encodings Subtitle Edit may export."""
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1256", "cp1252"):
        try:
            return parse_srt(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    return parse_srt(raw.decode("utf-8", errors="replace"))


def write_srt(entries: list[SubtitleEntry], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for e in reindex(entries):
        blocks.append(
            f"{e.index}\n{format_srt_timestamp(e.start)} --> "
            f"{format_srt_timestamp(e.end)}\n{e.text.strip()}\n"
        )
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def reindex(entries: list[SubtitleEntry]) -> list[SubtitleEntry]:
    return [replace(e, index=i + 1) for i, e in enumerate(entries)]


def clip_entries(
    entries: list[SubtitleEntry], clip_start: float, clip_end: float
) -> list[SubtitleEntry]:
    """Return entries overlapping [clip_start, clip_end], shifted to start at 0."""
    out: list[SubtitleEntry] = []
    for e in entries:
        if e.end <= clip_start or e.start >= clip_end:
            continue
        out.append(
            replace(
                e,
                start=max(e.start, clip_start) - clip_start,
                end=min(e.end, clip_end) - clip_start,
            )
        )
    return reindex(out)
