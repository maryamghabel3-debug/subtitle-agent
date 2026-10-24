from fa_subtitle_pipeline.media import (
    build_filtergraph,
    MediaInfo,
    output_dimensions,
    resolve_font_dir,
)


def test_output_dimensions_original_keeps_aspect():
    info = MediaInfo(duration=10, width=720, height=1280, has_audio=True)
    assert info.is_vertical
    assert output_dimensions(info, "original") == (720, 1280)
    assert output_dimensions(info, "vertical") == (1080, 1920)
    assert output_dimensions(info, "horizontal") == (1920, 1080)


def test_filtergraph_original_is_ass_only(tmp_path):
    info = MediaInfo(10, 720, 1280, True)
    graph = build_filtergraph(tmp_path / "x.ass", tmp_path, info, "original")
    assert graph.startswith("[0:v]ass=")
    assert "fontsdir=" in graph


def test_resolve_font_dir(tmp_path):
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "Vazirmatn-Bold.ttf").write_bytes(b"x")
    assert resolve_font_dir(fonts) == fonts
    assert resolve_font_dir("nope", search_roots=[tmp_path]) == fonts
    assert resolve_font_dir("nope", search_roots=[]) is None
