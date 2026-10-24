"""Speech-to-text with faster-whisper (optional dependency)."""
from __future__ import annotations

from pathlib import Path

from .config import PipelineConfig
from .srt_io import SubtitleEntry, write_srt


def _resolve_device(cfg: PipelineConfig) -> tuple[str, str]:
    device = cfg.whisper_device
    if device == "auto":
        try:
            import ctranslate2

            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    compute = cfg.whisper_compute_type
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"
    return device, compute


def transcribe(media: Path, cfg: PipelineConfig) -> list[SubtitleEntry]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper نصب نیست. برای ساخت زیرنویس از روی صدا اجرا کنید:\n"
            '  pip install ".[whisper]"\n'
            "یا یک فایل زیرنویس آماده (مثلاً خروجی Subtitle Edit) با --en-srt بدهید."
        ) from exc
    device, compute = _resolve_device(cfg)
    print(f"🎙️  Whisper [{cfg.whisper_model}] روی {device} ({compute}) ...")
    model = WhisperModel(cfg.whisper_model, device=device, compute_type=compute)
    language = cfg.source_language
    if language and language.lower() in ("auto", "detect"):
        language = None  # let Whisper detect the spoken language
    segments, _info = model.transcribe(
        str(media), language=language or None, vad_filter=True
    )
    entries = [
        SubtitleEntry(i + 1, float(s.start), float(s.end), s.text.strip())
        for i, s in enumerate(segments) if s.text.strip()
    ]
    print(f"🎙️  {len(entries)} خط زیرنویس استخراج شد.")
    return entries


def transcribe_to_srt(media: Path, out_srt: Path, cfg: PipelineConfig) -> Path:
    return write_srt(transcribe(media, cfg), out_srt)
