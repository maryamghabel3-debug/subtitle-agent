import pytest

from fa_subtitle_pipeline.config import PipelineConfig
from fa_subtitle_pipeline.translate.openai_provider import parse_batch_response


def test_config_rejects_unknown_key():
    with pytest.raises(ValueError):
        PipelineConfig.from_dict({"not_a_setting": 1})


def test_config_from_dict():
    cfg = PipelineConfig.from_dict({"part_duration": 90, "position": "top"})
    assert cfg.part_duration == 90
    assert cfg.position == "top"


def test_parse_json_array():
    assert parse_batch_response('["سلام", "خداحافظ"]', 2) == ["سلام", "خداحافظ"]


def test_parse_fenced_json():
    assert parse_batch_response('```json\n["سلام"]\n```', 1) == ["سلام"]


def test_parse_numbered_lines_fallback():
    assert parse_batch_response("1. سلام\n2) خداحافظ", 2) == ["سلام", "خداحافظ"]


def test_parse_wrong_count_raises():
    with pytest.raises(ValueError):
        parse_batch_response('["فقط یکی"]', 3)
