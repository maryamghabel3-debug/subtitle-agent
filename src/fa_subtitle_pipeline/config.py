"""Pipeline configuration (dataclass + optional YAML file)."""
from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path


@dataclass
class PipelineConfig:
    # --- languages -------------------------------------------------------
    source_language: str = "en"
    target_language: str = "fa"

    # --- transcription (Whisper, only when no SRT is provided) -----------
    whisper_model: str = "small"        # tiny|base|small|medium|large-v3|turbo
    whisper_device: str = "auto"        # auto|cuda|cpu
    whisper_compute_type: str = "auto"  # auto|float16|int8

    # --- translation -----------------------------------------------------
    # manual : stop at a checkpoint, you (or an AI chat) translate the .srt
    # auto   : openai when the API-key env var is set, otherwise manual
    # google : free Google Translate via deep-translator (quality: medium)
    # openai : any OpenAI-compatible Chat Completions API (needs an API key)
    # none   : the provided SRT is already Persian
    translation_provider: str = "manual"
    translation_model: str = "gpt-4o-mini"
    translation_api_base: str = "https://api.openai.com/v1"
    translation_api_key_env: str = "OPENAI_API_KEY"
    translation_batch_size: int = 20
    # Extra style instruction, e.g. "محاوره‌ای و خودمانی" or "رسمی و آموزشی".
    translation_style: str = "ساده، روان و مناسب زیرنویس؛ جمله‌ها کوتاه باشند"

    # --- Persian subtitle look -------------------------------------------
    font_name: str = "Vazirmatn"
    font_dir: str = "fonts"
    font_size: int | None = None        # None = auto from video height
    # above_english keeps the burned-in English line visible (bilingual),
    # Persian sits just above it. bottom/top place Persian at an edge.
    position: str = "above_english"
    margin_v: int | None = None         # manual override, in video pixels
    max_chars_per_line: int = 40
    primary_colour: str = "&H00FFFFFF"  # ASS colour: &HAABBGGRR
    outline_colour: str = "&H00000000"

    # --- outputs ---------------------------------------------------------
    # original keeps the input aspect ratio (vertical stays vertical...).
    # vertical makes a 1080x1920 blurred-background canvas, horizontal 1920x1080.
    output_mode: str = "original"
    make_full: bool = True              # full-length version (for YouTube)
    make_parts: bool = True             # ~1-minute parts (Reels / Shorts)
    part_duration: float = 60.0         # target seconds per part
    part_min_duration: float = 30.0
    part_max_duration: float = 90.0
    # subtitle: cut at the subtitle boundary nearest the target (legacy)
    # pause   : cut on natural pauses (subtitle gaps + real silences +
    #           sentence endings); suggested cuts are written to the work
    #           dir either way, and `run --cuts FILE` uses an approved file.
    split_mode: str = "subtitle"        # subtitle | pause
    silence_noise_db: float = -35.0     # silencedetect threshold (dB)
    silence_min_duration: float = 0.6   # silencedetect minimum length (s)
    pause_min_gap: float = 0.5          # min subtitle gap counted as a pause
    show_part_title: bool = True
    part_title_template: str = "قسمت {n} از {total}"

    # --- encoding --------------------------------------------------------
    video_codec: str = "libx264"
    crf: int = 20
    preset: str = "medium"
    audio_codec: str = "aac"
    audio_bitrate: str = "160k"
    ffmpeg_path: str | None = None      # None = auto-detect
    ffprobe_path: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineConfig":
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(
                f"Unknown config keys: {sorted(unknown)}. "
                f"Valid keys: {sorted(known)}"
            )
        return cls(**{k: v for k, v in data.items() if v is not None})

    def apply_overrides(self, overrides: dict) -> "PipelineConfig":
        for key, value in overrides.items():
            if value is None:
                continue
            if not hasattr(self, key):
                raise ValueError(f"Unknown config key: {key}")
            setattr(self, key, value)
        return self


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> PipelineConfig:
    cfg = PipelineConfig()
    if path:
        import yaml  # PyYAML, the one mandatory dependency

        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Config file {path} must contain a YAML mapping")
        cfg = PipelineConfig.from_dict(data)
    if overrides:
        cfg.apply_overrides(overrides)
    return cfg
