"""Command-line interface: fa-subs run | transcribe | suggest-cuts | translate | burn | doctor"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import load_config
from .media import OUTPUT_MODES, find_ffmpeg, find_ffprobe
from .pipeline import PipelinePaused, run_pipeline
from .translate import ALL_PROVIDERS


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", help="مسیر فایل کانفیگ YAML (اختیاری؛ نمونه: config.example.yaml)")


def _overrides_from(args, names) -> dict:
    return {n: getattr(args, n) for n in names if getattr(args, n, None) is not None}


def _cmd_run(args) -> int:
    cfg = load_config(args.config, _overrides_from(args, [
        "translation_provider", "output_mode", "position", "part_duration",
        "part_min_duration", "part_max_duration", "split_mode",
        "silence_noise_db", "silence_min_duration", "pause_min_gap",
        "whisper_model", "font_size", "margin_v", "font_dir",
    ]))
    if args.no_full:
        cfg.make_full = False
    if args.no_parts:
        cfg.make_parts = False
    if args.no_part_title:
        cfg.show_part_title = False
    try:
        run_pipeline(args.video, cfg, en_srt=args.en_srt, fa_srt=args.fa_srt,
                     output_dir=args.output_dir, force=args.force,
                     cuts_file=args.cuts)
    except PipelinePaused as paused:
        print("\n" + str(paused))
        return 2
    return 0


def _cmd_transcribe(args) -> int:
    from . import media
    from .transcribe import transcribe_to_srt

    cfg = load_config(args.config, _overrides_from(args, ["whisper_model", "source_language"]))
    media_path = Path(args.video)
    work = Path(args.out).parent if args.out else Path(".")
    audio = media.extract_audio(
        media_path, work / f"{media_path.stem}.wav", media.find_ffmpeg(cfg.ffmpeg_path)
    )
    lang_tag = (cfg.source_language or "src").lower()
    if lang_tag in ("auto", "detect"):
        lang_tag = "src"
    out = Path(args.out) if args.out else Path(f"{media_path.stem}.{lang_tag}.srt")
    transcribe_to_srt(audio, out, cfg)
    print(f"✅ {out}")
    return 0


def _cmd_suggest_cuts(args) -> int:
    from . import media
    from .cuts import format_hms, suggest_segments, write_cuts_file
    from .srt_io import read_srt

    cfg = load_config(args.config, _overrides_from(args, [
        "silence_noise_db", "silence_min_duration", "pause_min_gap",
    ]))
    video = Path(args.video)
    if not video.exists():
        raise FileNotFoundError(f"ویدیو پیدا نشد: {video}")
    ffmpeg = media.find_ffmpeg(cfg.ffmpeg_path)
    ffprobe = media.find_ffprobe(cfg.ffprobe_path)
    info = media.probe(video, ffmpeg, ffprobe)
    entries = read_srt(args.srt) if args.srt else []
    try:
        silences = media.detect_silences(
            video,
            ffmpeg,
            noise_db=cfg.silence_noise_db,
            min_silence=cfg.silence_min_duration,
        )
    except RuntimeError as exc:
        print(f"⚠️  تشخیص سکوت انجام نشد ({exc})؛ فقط از مکث بین زیرنویس‌ها استفاده می‌شود.")
        silences = []
    segments = suggest_segments(
        entries,
        silences,
        info.duration,
        target_duration=args.target,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        min_gap=cfg.pause_min_gap,
    )
    out = Path(args.out) if args.out else Path(f"{video.stem}.cuts.suggested.txt")
    write_cuts_file(out, segments, entries)
    print(f"🎬 مدت ویدیو: {format_hms(info.duration)}")
    print(f"🔇 {len(silences)} بازهٔ سکوت صوتی پیدا شد.")
    for seg in segments:
        print(
            f"  قسمت {seg.index}: {format_hms(seg.start)} → "
            f"{format_hms(seg.end)} ({seg.duration:.1f} ثانیه)"
        )
    print(f"✅ فایل برش‌های پیشنهادی: {out}")
    print("آن را بازبینی/ویرایش کنید و در اجرای نهایی با --cuts بدهید.")
    return 0


def _cmd_translate(args) -> int:
    from .srt_io import read_srt, write_srt
    from .translate import get_provider

    cfg = load_config(args.config, _overrides_from(args, ["translation_provider"]))
    provider = get_provider(cfg)
    if provider is None:
        if cfg.translation_provider == "auto":
            print(
                "⚠️  حالت auto است ولی کلید API تنظیم نشده؛ برای ترجمه خودکار "
                "کلید را تنظیم کنید یا --provider google/openai بگذارید."
            )
        else:
            print("⚠️  برای ترجمه خودکار --provider را auto، google یا openai بگذارید.")
        return 2
    entries = provider.translate(read_srt(args.input))
    write_srt(entries, args.out)
    print(f"✅ {args.out} ({len(entries)} خط)")
    return 0


def _cmd_burn(args) -> int:
    cfg = load_config(args.config, _overrides_from(args, [
        "output_mode", "position", "font_size", "margin_v", "font_dir",
    ]))
    cfg.make_full, cfg.make_parts = True, False
    result = run_pipeline(
        args.video, cfg, fa_srt=args.fa_srt,
        output_dir=str(Path(args.out).parent), force=args.force,
    )
    if result.full_video and Path(result.full_video) != Path(args.out):
        shutil.move(str(result.full_video), args.out)
        print(f"✅ {args.out}")
    return 0


def _cmd_doctor(args) -> int:
    cfg = load_config(args.config)
    ok = True

    def check(label, good, detail=""):
        nonlocal ok
        ok = ok and good
        print(f"{'✅' if good else '❌'} {label} {detail}".rstrip())

    try:
        ffmpeg = find_ffmpeg(cfg.ffmpeg_path)
        check("ffmpeg", True, f"({ffmpeg})")
        import subprocess

        build = subprocess.run([ffmpeg, "-hide_banner", "-version"],
                               capture_output=True, text=True).stdout
        check("libass در ffmpeg (لازم برای زیرنویس فارسی)", "--enable-libass" in build)
    except RuntimeError as exc:
        check("ffmpeg", False, str(exc))
    ffprobe = find_ffprobe(cfg.ffprobe_path)
    print(f"{'✅' if ffprobe else 'ℹ️ '} ffprobe {ffprobe or '(نیست؛ اشکالی ندارد، جایگزین داخلی استفاده می‌شود)'}")
    from .media import resolve_font_dir

    font_dir = resolve_font_dir(cfg.font_dir) or Path(cfg.font_dir)
    fonts = list(font_dir.glob("*.ttf")) if font_dir.exists() else []
    check(f"فونت فارسی در {font_dir}", bool(fonts),
          f"({', '.join(f.name for f in fonts)})" if fonts else "— اسکریپت scripts/download_font.py را اجرا کنید")
    print(f"{'✅' if importlib.util.find_spec('faster_whisper') else 'ℹ️ '} faster-whisper "
          f"{'(نصب است)' if importlib.util.find_spec('faster_whisper') else '(نصب نیست؛ فقط وقتی لازم است فایل srt ندارید)'}")
    print(f"{'✅' if importlib.util.find_spec('deep_translator') else 'ℹ️ '} deep-translator "
          f"{'(نصب است)' if importlib.util.find_spec('deep_translator') else '(نصب نیست؛ فقط برای --provider google)'}")
    has_key = bool(os.environ.get(cfg.translation_api_key_env))
    print(f"{'✅' if has_key else 'ℹ️ '} کلید API ({cfg.translation_api_key_env}) "
          f"{'(تنظیم شده)' if has_key else '(تنظیم نشده؛ برای --provider auto/openai لازم است)'}")
    print("\nهمه‌چیز برای شروع آماده است 🎉" if ok else "\n⚠️ موارد ❌ را از README رفع کنید.")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fa-subs",
        description="زیرنویس چسبیده فارسی + برش مکث‌محور برای ریلز/شورتس و نسخه کامل یوتیوب",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="اجرای کامل پایپ‌لاین روی یک ویدیو")
    p.add_argument("video")
    p.add_argument("--en-srt", help="زیرنویس زبان مبدأ آماده (نام گزینه برای سازگاری en مانده)؛ اگر ندهید با Whisper ساخته می‌شود")
    p.add_argument("--fa-srt", help="زیرنویس فارسی آماده؛ اگر بدهید مرحله ترجمه رد می‌شود")
    p.add_argument("--cuts", help="فایل برش‌های تأییدشده (.txt یا .json)؛ اگر بدهید دقیقاً همان برش‌ها استفاده می‌شوند")
    p.add_argument("--output-dir", help="پوشه خروجی (پیش‌فرض: output/<نام ویدیو>)")
    p.add_argument("--provider", dest="translation_provider", choices=ALL_PROVIDERS,
                   help="روش ترجمه: manual=دستی/چت، auto=API اگر کلید بود وگرنه دستی، google/openai=خودکار")
    p.add_argument("--output-mode", choices=OUTPUT_MODES,
                   help="original=ابعاد خود ویدیو (پیش‌فرض) | vertical=۹:۱۶ | horizontal=۱۶:۹")
    p.add_argument("--position", choices=("above_english", "bottom", "top"),
                   help="جای زیرنویس فارسی (پیش‌فرض: above_english یعنی بالای انگلیسی)")
    p.add_argument("--part-duration", type=float, help="طول هدف هر قسمت به ثانیه (پیش‌فرض: ۶۰)")
    p.add_argument("--part-min-duration", type=float, help="کوتاه‌ترین طول مجاز قسمت به ثانیه")
    p.add_argument("--part-max-duration", type=float, help="بلندترین طول مجاز قسمت به ثانیه")
    p.add_argument("--split-mode", choices=("subtitle", "pause"),
                   help="subtitle=نزدیک‌ترین مرز زیرنویس؛ pause=مکث طبیعی/سکوت/پایان جمله")
    p.add_argument("--silence-noise-db", type=float, help="آستانه تشخیص سکوت به dB (پیش‌فرض: -35)")
    p.add_argument("--silence-min-duration", type=float, help="حداقل طول سکوت به ثانیه (پیش‌فرض: 0.6)")
    p.add_argument("--pause-min-gap", type=float, help="حداقل فاصله بین دو زیرنویس برای مکث (پیش‌فرض: 0.5)")
    p.add_argument("--whisper-model", help="مدل Whisper (پیش‌فرض: small)")
    p.add_argument("--font-size", type=int)
    p.add_argument("--margin-v", type=int, help="فاصله زیرنویس فارسی از لبه، به پیکسل")
    p.add_argument("--font-dir")
    p.add_argument("--no-full", action="store_true", help="نسخه کامل ساخته نشود")
    p.add_argument("--no-parts", action="store_true", help="قسمت‌های کوتاه ساخته نشود")
    p.add_argument("--no-part-title", action="store_true", help="عنوان «قسمت n از m» نیاید")
    p.add_argument("--force", action="store_true", help="نادیده گرفتن کش فایل‌های میانی")
    _add_common(p)
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("transcribe", help="فقط ساخت زیرنویس از روی صدای گفتار (Whisper)")
    p.add_argument("video")
    p.add_argument("--out", help="مسیر خروجی .srt")
    p.add_argument("--whisper-model")
    p.add_argument("--language", dest="source_language",
                   help="زبان گفتار مثل en یا zh؛ auto یعنی تشخیص خودکار")
    _add_common(p)
    p.set_defaults(func=_cmd_transcribe)

    p = sub.add_parser("suggest-cuts", help="پیشنهاد برش قسمت‌ها از روی مکث‌ها و سکوت‌ها (برای بازبینی شما)")
    p.add_argument("video")
    p.add_argument("--srt", help="زیرنویس زبان مبدأ (اختیاری، ولی دقت پیشنهاد را بالا می‌برد)")
    p.add_argument("--out", help="مسیر خروجی .txt یا .json (پیش‌فرض: <نام ویدیو>.cuts.suggested.txt)")
    p.add_argument("--target", type=float, default=90.0, help="طول هدف هر قسمت به ثانیه (پیش‌فرض: 90)")
    p.add_argument("--min-duration", type=float, default=45.0, help="کوتاه‌ترین قسمت (پیش‌فرض: 45)")
    p.add_argument("--max-duration", type=float, default=150.0, help="بلندترین قسمت (پیش‌فرض: 150)")
    p.add_argument("--silence-noise-db", type=float, help="آستانه تشخیص سکوت به dB")
    p.add_argument("--silence-min-duration", type=float, help="حداقل طول سکوت به ثانیه")
    p.add_argument("--pause-min-gap", type=float, help="حداقل فاصله بین دو زیرنویس برای مکث")
    _add_common(p)
    p.set_defaults(func=_cmd_suggest_cuts)

    p = sub.add_parser("translate", help="ترجمه یک فایل srt به فارسی (auto/google/openai)")
    p.add_argument("input")
    p.add_argument("--out", required=True)
    p.add_argument("--provider", dest="translation_provider", choices=ALL_PROVIDERS, default="google")
    _add_common(p)
    p.set_defaults(func=_cmd_translate)

    p = sub.add_parser("burn", help="چسباندن یک زیرنویس فارسی آماده روی ویدیو (بدون برش)")
    p.add_argument("video")
    p.add_argument("--fa-srt", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--output-mode", choices=OUTPUT_MODES)
    p.add_argument("--position", choices=("above_english", "bottom", "top"))
    p.add_argument("--font-size", type=int)
    p.add_argument("--margin-v", type=int)
    p.add_argument("--font-dir")
    p.add_argument("--force", action="store_true")
    _add_common(p)
    p.set_defaults(func=_cmd_burn)

    p = sub.add_parser("doctor", help="بررسی آماده بودن محیط (ffmpeg، فونت، کتابخانه‌ها)")
    _add_common(p)
    p.set_defaults(func=_cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        print(f"\n❌ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
