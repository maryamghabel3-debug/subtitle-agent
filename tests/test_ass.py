from fa_subtitle_pipeline.ass import auto_font_size, build_ass, escape_ass_text
from fa_subtitle_pipeline.srt_io import SubtitleEntry

ENTRIES = [SubtitleEntry(1, 1.0, 3.0, "سلام دنیا")]


def test_ass_contains_style_and_dialogue():
    ass = build_ass(ENTRIES, width=720, height=1280)
    assert "PlayResX: 720" in ass
    assert "Style: Persian,Vazirmatn" in ass
    assert "Dialogue: 0,0:00:01.00,0:00:03.00,Persian" in ass
    assert "سلام دنیا" in ass


def test_ass_title_event():
    ass = build_ass(ENTRIES, width=720, height=1280, title="قسمت ۱ از ۳")
    assert "قسمت ۱ از ۳" in ass
    assert ",Title," in ass


def test_positions_change_alignment():
    bottom = build_ass(ENTRIES, width=720, height=1280, position="bottom")
    top = build_ass(ENTRIES, width=720, height=1280, position="top")
    assert bottom != top


def test_escape_and_newline():
    assert escape_ass_text("a{b}\nc") == r"a\{b\}\Nc"


def test_auto_font_size_scales():
    assert auto_font_size(1280) > auto_font_size(720) >= 24
