from fa_subtitle_pipeline.config import PipelineConfig
from fa_subtitle_pipeline.cuts import (
    load_cuts,
    parse_timestamp,
    segments_from_cuts,
    suggest_segments,
    write_cuts_file,
)
from fa_subtitle_pipeline.media import parse_silencedetect
from fa_subtitle_pipeline.srt_io import SubtitleEntry
from fa_subtitle_pipeline.translate import get_provider
from fa_subtitle_pipeline.translate.openai_provider import OpenAIProvider


def entry(index, start, end, text):
    return SubtitleEntry(index=index, start=start, end=end, text=text)


def test_suggest_prefers_long_pause_after_sentence_end():
    entries = [
        entry(1, 0, 20, "first line"),
        entry(2, 21, 40, "second line"),
        entry(3, 41, 58, "short pause follows"),
        entry(4, 59, 70, "still talking"),
        entry(5, 71, 84, "This episode ends here."),
        entry(6, 88, 120, "next episode begins"),
        entry(7, 121, 170, "more dialogue"),
        entry(8, 171, 230, "final dialogue"),
    ]

    segments = suggest_segments(
        entries,
        [(84.0, 88.0)],
        duration=260,
        target_duration=75,
        min_duration=45,
        max_duration=120,
    )

    assert 84 < segments[0].end < 85
    assert segments[0].start == 0
    assert segments[-1].end == 260


def test_suggest_can_use_pure_silences_without_subtitles():
    segments = suggest_segments(
        [],
        [(80.0, 84.0), (170.0, 174.0)],
        duration=260,
        target_duration=90,
        min_duration=60,
        max_duration=130,
    )

    assert [(s.start, s.end) for s in segments] == [
        (0.0, 82.0),
        (82.0, 172.0),
        (172.0, 260.0),
    ]


def test_suggest_falls_back_to_nearest_cue_end():
    entries = [
        entry(1, 0, 50, "continuous"),
        entry(2, 50, 100, "continuous"),
        entry(3, 100, 150, "continuous"),
        entry(4, 150, 200, "continuous"),
    ]

    segments = suggest_segments(
        entries,
        [],
        duration=220,
        target_duration=90,
        min_duration=60,
        max_duration=120,
    )

    assert [s.end for s in segments] == [100, 220]


def test_segments_from_cuts_filters_and_sorts():
    segments = segments_from_cuts([170, 83.4, 83.4, -1, 240], duration=240)

    assert [(s.start, s.end) for s in segments] == [
        (0.0, 83.4),
        (83.4, 170.0),
        (170.0, 240.0),
    ]


def test_parse_timestamp_formats_and_persian_digits():
    assert parse_timestamp("00:01:23.400") == 83.4
    assert parse_timestamp("۱:۲۳") == 83
    assert parse_timestamp("83,4") == 83.4


def test_cuts_txt_round_trip(tmp_path):
    entries = [
        entry(1, 75, 83, "Last line of part one."),
        entry(2, 86, 100, "First line of part two"),
        entry(3, 160, 169, "Last line of part two."),
        entry(4, 173, 190, "First line of part three"),
    ]
    segments = segments_from_cuts([83.4, 170.0], duration=240)
    path = write_cuts_file(tmp_path / "cuts.txt", segments, entries)

    text = path.read_text(encoding="utf-8")
    assert "نقاط برش پیشنهادی" in text
    loaded = load_cuts(path, duration=240)
    assert [(s.start, s.end) for s in loaded] == [
        (s.start, s.end) for s in segments
    ]


def test_cuts_json_round_trip(tmp_path):
    segments = segments_from_cuts([90, 180], duration=260)
    path = write_cuts_file(tmp_path / "cuts.json", segments, [])
    loaded = load_cuts(path, duration=260)

    assert [(s.start, s.end) for s in loaded] == [
        (s.start, s.end) for s in segments
    ]


def test_load_cuts_ignores_comments(tmp_path):
    path = tmp_path / "approved.txt"
    path.write_text(
        "# برش‌های تأییدشده\n"
        "۰۰:۰۱:۱۰  # پایان قسمت اول\n"
        "00:02:00  # پایان قسمت دوم\n",
        encoding="utf-8",
    )

    segments = load_cuts(path, duration=180)

    assert [s.end for s in segments] == [70, 120, 180]


def test_parse_silencedetect_pairs_start_and_end():
    log = """
    [silencedetect @ 0x1] silence_start: 12.5
    [silencedetect @ 0x1] silence_end: 15.25 | silence_duration: 2.75
    [silencedetect @ 0x1] silence_start: 40
    """

    assert parse_silencedetect(log) == [(12.5, 15.25)]


def test_auto_provider_waits_without_key_and_uses_openai_with_key(monkeypatch):
    cfg = PipelineConfig(translation_provider="auto")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_provider(cfg) is None

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert isinstance(get_provider(cfg), OpenAIProvider)
