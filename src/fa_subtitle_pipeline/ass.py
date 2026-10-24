"""Generate ASS subtitle files styled for Persian (rendered by libass).

libass + FriBidi (bundled with standard FFmpeg builds) shape Persian text
correctly, so the text is written in logical order — no reshaper needed.
"""
from __future__ import annotations

from pathlib import Path

from .srt_io import SubtitleEntry, format_ass_timestamp
from .text_utils import wrap_text

POSITIONS = ("above_english", "bottom", "top")


def escape_ass_text(text: str) -> str:
    text = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    return text.replace("\n", r"\N")


def auto_font_size(height: int) -> int:
    """Roughly 3.5% of the frame height, readable on phones and TV alike."""
    return max(24, int(round(height * 0.035)))


def resolve_margin_v(position: str, height: int, explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    if position == "above_english":
        # Sit above the burned-in English line near the bottom edge.
        return int(round(height * 0.125))
    return int(round(height * 0.05))


def build_ass(
    entries: list[SubtitleEntry],
    width: int,
    height: int,
    font_name: str = "Vazirmatn",
    font_size: int | None = None,
    position: str = "above_english",
    margin_v: int | None = None,
    max_chars_per_line: int = 40,
    primary_colour: str = "&H00FFFFFF",
    outline_colour: str = "&H00000000",
    title: str | None = None,
    title_duration: float = 3.0,
) -> str:
    if position not in POSITIONS:
        raise ValueError(f"Unknown position {position!r}; choose one of {POSITIONS}")
    size = font_size or auto_font_size(height)
    margin = resolve_margin_v(position, height, margin_v)
    alignment = 8 if position == "top" else 2  # 8=top-center, 2=bottom-center
    margin_lr = max(16, int(round(width * 0.04)))
    title_size = int(round(size * 0.85))

    header = f"""[Script Info]
Title: Persian subtitles (fa-subtitle-pipeline)
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Persian,{font_name},{size},{primary_colour},&H000000FF,{outline_colour},&H64000000,-1,0,0,0,100,100,0,0,1,3,1,{alignment},{margin_lr},{margin_lr},{margin},1
Style: Title,{font_name},{title_size},&H00FFFFFF,&H000000FF,{outline_colour},&H64000000,-1,0,0,0,100,100,0,0,1,3,1,8,{margin_lr},{margin_lr},{int(round(height * 0.04))},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    if title:
        lines.append(
            f"Dialogue: 1,0:00:00.00,{format_ass_timestamp(title_duration)},"
            f"Title,,0,0,0,,{escape_ass_text(title)}"
        )
    for e in entries:
        text = escape_ass_text(wrap_text(e.text, max_chars_per_line))
        lines.append(
            f"Dialogue: 0,{format_ass_timestamp(e.start)},{format_ass_timestamp(e.end)},"
            f"Persian,,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"


def write_ass(path: str | Path, **kwargs) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_ass(**kwargs), encoding="utf-8")
    return path
