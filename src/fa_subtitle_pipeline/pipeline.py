"""End-to-end orchestration:

video ──(Whisper or provided SRT)──▶ EN subtitles ──(translate)──▶ FA subtitles
      ──▶ burn into a full video + smart ~1-minute parts

Intermediate files are cached in the work directory, so re-running after the
manual-translation checkpoint (or a crash) never repeats finished steps.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import media
from .ass import write_ass
from .config import PipelineConfig
from .segment import Segment, plan_segments
from .srt_io import SubtitleEntry, clip_entries, read_srt, write_srt
from .text_utils import normalize_persian, quality_warnings, similarity_ratio, to_persian_digits
from .translate import get_provider


class PipelinePaused(Exception):
    """Raised at the manual-translation checkpoint."""


@dataclass
class PipelineResult:
    full_video: Path | None = None
    parts: list[Path] = field(default_factory=list)
    en_srt: Path | None = None
    fa_srt: Path | None = None
    segments: list[Segment] = field(default_factory=list)


def _font_dir(cfg: PipelineConfig) -> Path | None:
    return media.resolve_font_dir(cfg.font_dir)


def _manual_checkpoint(work_dir: Path, stem: str, en_entries: list[SubtitleEntry]) -> None:
    template = work_dir / f"{stem}.fa.srt"
    write_srt(en_entries, template)
    (work_dir / "TRANSLATE_ME.md").write_text(
        "# ایستگاه ترجمه دستی ✋\n\n"
        f"فایل `{template.name}` ساخته شد. این یک قالب آماده است:\n"
        "زمان‌بندی‌ها درست است، فقط متن هر خط هنوز انگلیسی است.\n\n"
        "## چه کار کنم؟\n"
        "1. متن هر خط را به فارسی ترجمه کنید (خودتان، یا فایل را به یک "
        "دستیار هوش مصنوعی بدهید و بگویید «هر خط را کوتاه و مناسب زیرنویس "
        "به فارسی ترجمه کن و فایل srt برگردان»).\n"
        "2. فایل ترجمه‌شده را روی همین مسیر ذخیره کنید،\n"
        f"   یا هنگام اجرای دوباره مسیرش را بدهید: `--fa-srt {template}`\n"
        "3. دوباره همان دستور قبلی را اجرا کنید؛ کار از همین‌جا ادامه پیدا می‌کند.\n\n"
        "⚠️ شماره خطوط و زمان‌ها را تغییر ندهید، فقط متن‌ها.\n",
        encoding="utf-8",
    )
    raise PipelinePaused(
        "✋ ایستگاه ترجمه دستی\n"
        f"   قالب ترجمه ساخته شد: {template}\n"
        "   متن‌ها را به فارسی ترجمه کنید و دوباره همین دستور را اجرا کنید.\n"
        f"   راهنمای کامل: {work_dir / 'TRANSLATE_ME.md'}"
    )


def run_pipeline(
    video: str | Path,
    cfg: PipelineConfig,
    en_srt: str | Path | None = None,
    fa_srt: str | Path | None = None,
    output_dir: str | Path | None = None,
    force: bool = False,
) -> PipelineResult:
    video = Path(video)
    if not video.exists():
        raise FileNotFoundError(f"ویدیو پیدا نشد: {video}")
    stem = video.stem
    out_dir = Path(output_dir) if output_dir else Path("output") / stem
    work_dir = out_dir / "work"
    parts_dir = out_dir / "parts"
    work_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg = media.find_ffmpeg(cfg.ffmpeg_path)
    ffprobe = media.find_ffprobe(cfg.ffprobe_path)
    info = media.probe(video, ffmpeg, ffprobe)
    print(
        f"🎬 {video.name}: {info.width}x{info.height} "
        f"({'عمودی' if info.is_vertical else 'افقی/مربعی'})، {info.duration:.1f} ثانیه"
    )
    result = PipelineResult()

    # ---- 1) source (English) subtitles ----------------------------------
    en_path = work_dir / f"{stem}.en.srt"
    en_entries: list[SubtitleEntry] | None = None
    if en_srt:
        en_entries = read_srt(en_srt)
        write_srt(en_entries, en_path)
        print(f"📄 زیرنویس انگلیسی آماده استفاده شد: {en_srt} ({len(en_entries)} خط)")
    elif en_path.exists() and not force:
        en_entries = read_srt(en_path)
        print(f"📄 زیرنویس انگلیسی از کش خوانده شد: {en_path} ({len(en_entries)} خط)")
    elif not fa_srt:
        from .transcribe import transcribe  # lazy: optional dependency

        audio = media.extract_audio(video, work_dir / f"{stem}.wav", ffmpeg)
        en_entries = transcribe(audio, cfg)
        write_srt(en_entries, en_path)
    if en_path.exists():
        result.en_srt = en_path

    # ---- 2) Persian subtitles -------------------------------------------
    fa_path = work_dir / f"{stem}.fa.srt"
    if fa_srt:
        fa_entries = read_srt(fa_srt)
        write_srt(fa_entries, fa_path)
        print(f"📄 زیرنویس فارسی آماده استفاده شد: {fa_srt} ({len(fa_entries)} خط)")
    elif cfg.translation_provider == "none":
        assert en_entries is not None
        fa_entries = en_entries
        write_srt(fa_entries, fa_path)
    elif cfg.translation_provider == "manual":
        assert en_entries is not None
        if fa_path.exists() and not force:
            cached = read_srt(fa_path)
            if similarity_ratio(cached, en_entries) < 0.9:
                fa_entries = cached
                print(f"📄 ترجمه فارسی دستی پیدا شد: {fa_path} ({len(fa_entries)} خط)")
            else:
                _manual_checkpoint(work_dir, stem, en_entries)
        else:
            _manual_checkpoint(work_dir, stem, en_entries)
    else:
        assert en_entries is not None
        provider = get_provider(cfg)
        assert provider is not None
        fa_entries = provider.translate(en_entries)
        write_srt(fa_entries, fa_path)
    result.fa_srt = fa_path

    # Normalise + readability report
    from dataclasses import replace as _replace

    fa_entries = [_replace(e, text=normalize_persian(e.text)) for e in fa_entries]
    write_srt(fa_entries, fa_path)
    warnings = quality_warnings(fa_entries)
    if warnings:
        report = work_dir / "subtitle_warnings.txt"
        report.write_text("\n".join(warnings) + "\n", encoding="utf-8")
        print(f"⚠️  {len(warnings)} خط برای خواندن طولانی/سریع است؛ جزئیات: {report}")

    seg_entries = en_entries or fa_entries

    # ---- 3) burn-in: full video + parts ----------------------------------
    out_w, out_h = media.output_dimensions(info, cfg.output_mode)
    font_dir = _font_dir(cfg)
    if font_dir is None:
        print(f"⚠️  پوشه فونت پیدا نشد ({cfg.font_dir})؛ از فونت‌های سیستم استفاده می‌شود.")

    def _render(ass_path: Path, out: Path, start=None, duration=None) -> Path:
        return media.render(
            video, out, ass_path, info, ffmpeg=ffmpeg, font_dir=font_dir,
            output_mode=cfg.output_mode, start=start, duration=duration,
            video_codec=cfg.video_codec, crf=cfg.crf, preset=cfg.preset,
            audio_codec=cfg.audio_codec, audio_bitrate=cfg.audio_bitrate,
        )

    def _ass_kwargs(entries, title=None):
        return dict(
            entries=entries, width=out_w, height=out_h, font_name=cfg.font_name,
            font_size=cfg.font_size, position=cfg.position, margin_v=cfg.margin_v,
            max_chars_per_line=cfg.max_chars_per_line,
            primary_colour=cfg.primary_colour, outline_colour=cfg.outline_colour,
            title=title,
        )

    if cfg.make_full:
        full_ass = write_ass(work_dir / f"{stem}.fa.ass", **_ass_kwargs(fa_entries))
        result.full_video = _render(full_ass, out_dir / f"{stem}_full_fa.mp4")
        print(f"✅ نسخه کامل: {result.full_video}")

    if cfg.make_parts:
        segments = plan_segments(
            seg_entries, info.duration,
            target_duration=cfg.part_duration,
            min_duration=cfg.part_min_duration,
            max_duration=cfg.part_max_duration,
        )
        result.segments = segments
        total = len(segments)
        print(f"✂️  {total} قسمت ~{cfg.part_duration:.0f} ثانیه‌ای (برش روی پایان جمله‌ها)")
        for seg in segments:
            title = None
            if cfg.show_part_title and total > 1:
                title = to_persian_digits(
                    cfg.part_title_template.format(n=seg.index, total=total)
                )
            clipped = clip_entries(fa_entries, seg.start, seg.end)
            part_ass = write_ass(
                work_dir / f"{stem}_part-{seg.index:02d}.ass",
                **_ass_kwargs(clipped, title=title),
            )
            part_out = _render(
                part_ass, parts_dir / f"{stem}_part-{seg.index:02d}.mp4",
                start=seg.start, duration=seg.duration,
            )
            result.parts.append(part_out)
            print(f"✅ قسمت {seg.index}/{total}: {part_out} ({seg.start:.1f}→{seg.end:.1f}s)")

    # ---- 4) manifest + caption template ----------------------------------
    manifest = {
        "video": str(video), "width": info.width, "height": info.height,
        "duration": info.duration, "output_mode": cfg.output_mode,
        "full_video": str(result.full_video) if result.full_video else None,
        "parts": [str(p) for p in result.parts],
        "segments": [{"part": s.index, "start": s.start, "end": s.end} for s in result.segments],
        "en_srt": str(result.en_srt) if result.en_srt else None,
        "fa_srt": str(result.fa_srt) if result.fa_srt else None,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    captions = []
    for i, part in enumerate(result.parts, 1):
        captions.append(
            f"--- {part.name} ---\n"
            f"قسمت {to_persian_digits(str(i))} از {to_persian_digits(str(len(result.parts)))} 🎬\n"
            "(کپشن را اینجا بنویسید)\n#زیرنویس_فارسی\n"
        )
    if captions:
        (out_dir / "captions.txt").write_text("\n".join(captions), encoding="utf-8")
    print(f"🎉 تمام شد! خروجی‌ها در: {out_dir}")
    return result
