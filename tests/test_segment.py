from fa_subtitle_pipeline.segment import plan_segments
from fa_subtitle_pipeline.srt_io import SubtitleEntry


def _entries(ends):
    return [
        SubtitleEntry(i + 1, max(0.0, end - 2), float(end), f"line {i}")
        for i, end in enumerate(ends)
    ]


def test_cut_snaps_to_sentence_end():
    # Subtitle boundaries at 58 and 125; target cuts at 60/120 snap to them.
    segs = plan_segments(_entries([20, 40, 58, 90, 125, 160, 179]),
                         video_duration=180, target_duration=60,
                         min_duration=30, max_duration=90)
    assert [round(s.end) for s in segs] == [58, 125, 180]
    assert segs[0].start == 0
    assert segs[1].start == segs[0].end


def test_no_subtitles_plain_chunks():
    segs = plan_segments([], video_duration=150, target_duration=60,
                         min_duration=30, max_duration=90)
    assert [round(s.end) for s in segs] == [60, 150]


def test_no_tiny_trailing_part():
    segs = plan_segments([], video_duration=75, target_duration=60,
                         min_duration=30, max_duration=90)
    assert len(segs) == 1 and segs[0].end == 75


def test_short_video_single_part():
    segs = plan_segments([], video_duration=45)
    assert len(segs) == 1
