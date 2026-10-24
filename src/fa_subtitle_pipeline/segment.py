"""Smart splitting of a video into parts.

Cuts are snapped to the end of a subtitle line closest to the target
duration, so a part never ends in the middle of a sentence when a subtitle
boundary is available nearby.
"""
from __future__ import annotations

from dataclasses import dataclass

from .srt_io import SubtitleEntry


@dataclass
class Segment:
    index: int  # 1-based
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def plan_segments(
    entries: list[SubtitleEntry],
    video_duration: float,
    target_duration: float = 60.0,
    min_duration: float = 30.0,
    max_duration: float = 90.0,
) -> list[Segment]:
    if video_duration <= 0:
        return []
    if max_duration < target_duration:
        max_duration = target_duration
    if min_duration > target_duration:
        min_duration = target_duration

    boundaries = sorted({e.end for e in entries if 0 < e.end < video_duration})
    segments: list[Segment] = []
    start = 0.0
    while start < video_duration - 0.05:
        remaining = video_duration - start
        if remaining <= max_duration:
            segments.append(Segment(len(segments) + 1, start, video_duration))
            break
        ideal = start + target_duration
        candidates = [
            b for b in boundaries
            if start + min_duration <= b <= start + max_duration
        ]
        end = min(candidates, key=lambda b: abs(b - ideal)) if candidates else ideal
        # Avoid leaving a tiny trailing part: absorb it into this one.
        if video_duration - end < min_duration:
            end = video_duration
        segments.append(Segment(len(segments) + 1, start, end))
        start = end
    return segments
