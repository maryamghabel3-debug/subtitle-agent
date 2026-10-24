from fa_subtitle_pipeline.srt_io import SubtitleEntry
from fa_subtitle_pipeline.text_utils import (
    normalize_persian,
    quality_warnings,
    similarity_ratio,
    to_persian_digits,
    wrap_text,
)


def test_normalize_arabic_glyphs():
    # Arabic Yeh/Kaf become Persian Yeh/Kaf; markup is removed.
    assert normalize_persian("<i>يك كتاب</i>") == "یک کتاب"


def test_persian_digits():
    assert to_persian_digits("Part 12") == "Part ۱۲"


def test_wrap_text_respects_limits():
    text = "این یک جمله نسبتا طولانی برای تست شکستن خطوط زیرنویس است"
    wrapped = wrap_text(text, max_chars_per_line=20, max_lines=2)
    lines = wrapped.split("\n")
    assert len(lines) == 2
    assert len(lines[0]) <= 20


def test_quality_warnings_flags_fast_subtitle():
    entries = [SubtitleEntry(1, 0.0, 1.0, "این یک متن خیلی خیلی طولانی برای یک ثانیه است")]
    assert quality_warnings(entries)


def test_similarity_ratio_detects_untranslated_template():
    a = [SubtitleEntry(1, 0, 1, "Hello"), SubtitleEntry(2, 1, 2, "World")]
    assert similarity_ratio(a, a) == 1.0
    b = [SubtitleEntry(1, 0, 1, "سلام"), SubtitleEntry(2, 1, 2, "دنیا")]
    assert similarity_ratio(a, b) == 0.0
