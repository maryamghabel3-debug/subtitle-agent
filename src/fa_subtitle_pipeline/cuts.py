"""Pause-aware cut suggestions for splitting long videos into parts.

The user asked for parts whose lengths may vary: a part should end where the
video naturally pauses — a silence / a gap between two subtitle lines, ideally
right after a finished sentence — not at an exact fixed second. This module

1. collects candidate cut points from subtitle gaps, real audio silences
   (ffmpeg silencedetect) and sentence endings,
2. greedily picks the best candidate near each target duration, and
3. reads/writes a small, human-editable cuts file so the user can review and
   approve (or move/delete) the suggested cuts before rendering.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .segment import Segment
from .srt_io import SubtitleEntry, format_srt_timestamp

SENTENCE_ENDINGS = ".!?…؟。！？"

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


@dataclass
class CutCandidate:
    time: float
    gap: float = 0.0          # pause until the next subtitle line, seconds
    silence: float = 0.0      # overlapping real audio silence, seconds
    sentence_end: bool = False
    last_text: str = ""


def is_sentence_end(text: str) -> bool:
    t = text.strip().rstrip("\"'»)]}»’”").strip()
    return bool(t) and t[-1] in SENTENCE_ENDINGS


def _silence_overlap(start: float, end: float, silences) -> float:
    total = 0.0
    for s, e in silences:
        total += max(0.0, min(end, e) - max(start, s))
    return total


def find_candidates(
    entries: list[SubtitleEntry],
    silences: list[tuple[float, float]],
    duration: float,
    min_gap: float = 0.5,
) -> list[CutCandidate]:
    """Candidate cut points: subtitle-gap pauses, sentence ends, silences."""
    ordered = sorted(entries, key=lambda e: (e.start, e.end))
    candidates: list[CutCandidate] = []
    for i, entry in enumerate(ordered):
        if entry.end <= 0 or entry.end >= duration:
            continue
        next_start = ordered[i + 1].start if i + 1 < len(ordered) else duration
        gap = max(0.0, next_start - entry.end)
        silence = _silence_overlap(entry.end, next_start, silences)
        sentence = is_sentence_end(entry.text)
        if gap >= min_gap or silence >= min_gap or sentence:
            # Cut shortly after the line ends, inside the pause.
            t = entry.end + min(gap / 2, 0.5)
            if 0 < t < duration:
                candidates.append(CutCandidate(t, gap, silence, sentence, entry.text))
    # Long pure silences with no subtitle over them (scene/episode breaks).
    for s, e in silences:
        length = e - s
        if length < max(1.2, min_gap):
            continue
        mid = (s + e) / 2
        if not 0 < mid < duration:
            continue
        if any(en.start < mid < en.end for en in ordered):
            continue
        if any(abs(c.time - mid) < 1.0 for c in candidates):
            continue
        prev_text = ""
        for en in ordered:
            if en.end <= mid:
                prev_text = en.text
            else:
                break
        candidates.append(CutCandidate(mid, length, length, False, prev_text))
    # Sort + de-duplicate near-identical times, keeping the stronger pause.
    candidates.sort(key=lambda c: c.time)
    deduped: list[CutCandidate] = []
    for c in candidates:
        if deduped and c.time - deduped[-1].time < 0.3:
            if (c.gap + c.silence) > (deduped[-1].gap + deduped[-1].silence):
                deduped[-1] = c
        else:
            deduped.append(c)
    return deduped


def _candidate_score(candidate: CutCandidate, ideal: float, target: float) -> float:
    score = min(candidate.gap, 4.0) * 2.0
    score += min(candidate.silence, 4.0) * 1.5
    score += 2.0 if candidate.sentence_end else 0.0
    score -= abs(candidate.time - ideal) / max(target, 1.0) * 3.0
    return score


def suggest_segments(
    entries: list[SubtitleEntry],
    silences: list[tuple[float, float]],
    duration: float,
    target_duration: float = 90.0,
    min_duration: float = 45.0,
    max_duration: float = 150.0,
    min_gap: float = 0.5,
) -> list[Segment]:
    """Plan parts so each cut lands on a natural pause near the target."""
    if duration <= 0:
        return []
    if max_duration < target_duration:
        max_duration = target_duration
    if min_duration > target_duration:
        min_duration = target_duration
    candidates = find_candidates(entries, silences, duration, min_gap=min_gap)
    cue_ends = sorted({e.end for e in entries if 0 < e.end < duration})

    segments: list[Segment] = []
    start = 0.0
    while start < duration - 0.05:
        if duration - start <= max_duration:
            segments.append(Segment(len(segments) + 1, start, duration))
            break
        ideal = start + target_duration
        window = [c for c in candidates
                  if start + min_duration <= c.time <= start + max_duration]
        if window:
            end = max(window, key=lambda c: _candidate_score(c, ideal, target_duration)).time
        else:
            pool = [t for t in (cue_ends + [c.time for c in candidates])
                    if start + min_duration * 0.5 <= t <= start + max_duration * 1.3]
            end = min(pool, key=lambda t: abs(t - ideal)) if pool else ideal
        if end <= start + 1.0:
            end = min(start + target_duration, duration)
        if duration - end < min_duration:  # absorb a tiny trailing part
            end = duration
        segments.append(Segment(len(segments) + 1, start, end))
        start = end
    return segments


def segments_from_cuts(cuts: list[float], duration: float) -> list[Segment]:
    points = sorted({round(float(c), 3) for c in cuts if 0.05 < float(c) < duration - 0.05})
    segments: list[Segment] = []
    start = 0.0
    for point in points:
        segments.append(Segment(len(segments) + 1, start, point))
        start = point
    segments.append(Segment(len(segments) + 1, start, duration))
    return segments


# --------------------------------------------------------------------------
# Cuts files: a friendly .txt (one HH:MM:SS per line) or structured .json
# --------------------------------------------------------------------------

def format_hms(seconds: float) -> str:
    return format_srt_timestamp(seconds).replace(",", ".")


def parse_timestamp(token: str) -> float:
    """Parse '83.4', '1:23', '00:01:23.4' (Persian/Arabic digits allowed)."""
    token = token.strip().translate(_DIGIT_MAP).replace(",", ".")
    if not token:
        raise ValueError("زمان خالی است")
    parts = token.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError as exc:
        raise ValueError(f"زمان قابل خواندن نیست: {token!r}") from exc
    if len(nums) == 1:
        return nums[0]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    raise ValueError(f"زمان قابل خواندن نیست: {token!r}")


def _describe_cut(cut: float, entries: list[SubtitleEntry]) -> str:
    ordered = sorted(entries, key=lambda e: (e.start, e.end))
    prev = None
    for entry in ordered:
        if entry.end <= cut + 0.75:
            prev = entry
        else:
            break
    parts: list[str] = []
    if prev is not None:
        nxt = next((e for e in ordered if e.start >= prev.end and e is not prev), None)
        if nxt is not None and nxt.start - prev.end >= 0.5:
            parts.append(f"مکث ~{nxt.start - prev.end:.1f} ثانیه")
        if is_sentence_end(prev.text):
            parts.append("پایان جمله")
        last = " ".join(prev.text.split())
        if len(last) > 70:
            last = last[:67] + "…"
        parts.append(f"آخرین دیالوگ: «{last}»")
    return "؛ ".join(parts)


def write_cuts_file(
    path: str | Path,
    segments: list[Segment],
    entries: list[SubtitleEntry] | None = None,
) -> Path:
    """Write suggested cuts. .json → structured; anything else → friendly txt."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = entries or []
    cuts = [s.end for s in segments[:-1]]  # last part runs to the video end
    if path.suffix.lower() == ".json":
        data = {
            "instructions_fa": (
                "هر مورد در cuts پایان یک قسمت است. می‌توانید زمان‌ها (ثانیه) را "
                "عوض کنید یا حذف/اضافه کنید؛ قسمت آخر همیشه تا پایان ویدیوست."
            ),
            "duration": segments[-1].end if segments else 0,
            "segments": [
                {"part": s.index, "start": round(s.start, 3), "end": round(s.end, 3)}
                for s in segments
            ],
            "cuts": [
                {
                    "end": round(c, 3),
                    "end_hms": format_hms(c),
                    "reason": _describe_cut(c, entries),
                }
                for c in cuts
            ],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    lines = [
        "# نقاط برش پیشنهادی — هر خط یعنی «پایان یک قسمت»",
        "# سیستم این نقاط را از روی مکث‌ها، سکوت‌ها و پایان جمله‌ها پیدا کرده است.",
        "# شما می‌توانید: زمان یک خط را جابه‌جا کنید، خطی را پاک کنید (قسمت‌ها یکی می‌شوند)،",
        "# یا خط تازه‌ای با فرمت ساعت:دقیقه:ثانیه اضافه کنید. قسمت آخر تا پایان ویدیوست.",
        "# هر چیزی بعد از علامت # توضیح است و خوانده نمی‌شود.",
        "",
    ]
    if not cuts:
        lines.append("# برشی پیشنهاد نشد؛ ویدیو یک قسمت کامل می‌شود.")
    for seg, cut in zip(segments, cuts):
        reason = _describe_cut(cut, entries)
        lines.append(f"{format_hms(cut)}  # پایان قسمت {seg.index}" + (f" — {reason}" if reason else ""))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load_cuts(path: str | Path, duration: float) -> list[Segment]:
    """Read an approved cuts file (.txt or .json) into segments."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"فایل برش‌ها پیدا نشد: {path}")
    cuts: list[float] = []
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        items: list = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if isinstance(data.get("cuts"), list):
                items = data["cuts"]
            elif isinstance(data.get("segments"), list):
                items = data["segments"]
        for item in items:
            if isinstance(item, (int, float)):
                cuts.append(float(item))
            elif isinstance(item, dict):
                value = item.get("end", item.get("time"))
                if isinstance(value, (int, float)):
                    cuts.append(float(value))
                elif isinstance(value, str):
                    cuts.append(parse_timestamp(value))
    else:
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            token = line.split("#", 1)[0].strip().split()[0]
            cuts.append(parse_timestamp(token))
    return segments_from_cuts(cuts, duration)
