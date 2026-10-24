from fa_subtitle_pipeline.srt_io import (
    SubtitleEntry,
    clip_entries,
    format_ass_timestamp,
    format_srt_timestamp,
    parse_srt,
    write_srt,
    read_srt,
)

SAMPLE = """1
00:00:01,000 --> 00:00:03,500
Hello world

2
00:00:04,000 --> 00:00:06,000
Second line
with two rows
"""


def test_parse_srt():
    entries = parse_srt(SAMPLE)
    assert len(entries) == 2
    assert entries[0].start == 1.0
    assert entries[0].end == 3.5
    assert entries[0].text == "Hello world"
    assert entries[1].text == "Second line\nwith two rows"


def test_parse_dot_milliseconds_and_vtt():
    entries = parse_srt("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi\n")
    assert len(entries) == 1
    assert entries[0].text == "Hi"


def test_timestamp_formatting():
    assert format_srt_timestamp(3661.25) == "01:01:01,250"
    assert format_ass_timestamp(3661.25) == "1:01:01.25"
    assert format_srt_timestamp(0) == "00:00:00,000"


def test_write_read_roundtrip(tmp_path):
    entries = parse_srt(SAMPLE)
    path = write_srt(entries, tmp_path / "x.srt")
    assert read_srt(path) == entries


def test_clip_entries_shifts_and_clips():
    entries = [
        SubtitleEntry(1, 0.0, 5.0, "a"),
        SubtitleEntry(2, 5.0, 10.0, "b"),
        SubtitleEntry(3, 10.0, 15.0, "c"),
    ]
    clipped = clip_entries(entries, 4.0, 12.0)
    assert [e.text for e in clipped] == ["a", "b", "c"]
    assert clipped[0].start == 0.0 and clipped[0].end == 1.0
    assert clipped[1].start == 1.0 and clipped[1].end == 6.0
    assert clipped[2].start == 6.0 and clipped[2].end == 8.0
    assert [e.index for e in clipped] == [1, 2, 3]
