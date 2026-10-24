"""FFmpeg/ffprobe wrappers: probing, audio extraction, subtitle burning."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

OUTPUT_MODES = ("original", "vertical", "horizontal")


@dataclass
class MediaInfo:
    duration: float
    width: int
    height: int
    has_audio: bool

    @property
    def is_vertical(self) -> bool:
        return self.height > self.width


def find_ffmpeg(configured: str | None = None) -> str:
    if configured:
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:  # Handy fallback: a static build shipped by imageio-ffmpeg.
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    raise RuntimeError(
        "ffmpeg پیدا نشد! اول FFmpeg را نصب کنید (راهنما در README) "
        "یا مسیر آن را در کانفیگ با ffmpeg_path بدهید."
    )


def find_ffprobe(configured: str | None = None) -> str | None:
    return configured or shutil.which("ffprobe")


def resolve_font_dir(
    configured: str | Path = "fonts", search_roots: list[Path] | None = None
) -> Path | None:
    """Locate the fonts directory: as configured, via $FA_SUBS_FONT_DIR, or
    next to the installed package (works from any working directory)."""
    import os

    requested = Path(configured).expanduser()
    if requested.exists():
        return requested
    env = os.environ.get("FA_SUBS_FONT_DIR")
    if env and Path(env).exists():
        return Path(env)
    roots = search_roots
    if roots is None:
        roots = [Path.cwd(), *Path(__file__).resolve().parents]
    for root in roots:
        for candidate in (root / requested, root / "fonts"):
            if candidate.exists() and any(candidate.glob("*.ttf")):
                return candidate
    return None


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print("▶", " ".join(str(c) for c in cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        tail = "\n".join((result.stderr or "").strip().splitlines()[-25:])
        raise RuntimeError(f"ffmpeg با خطا متوقف شد:\n{tail}")
    return result


def probe(path: str | Path, ffmpeg: str, ffprobe: str | None = None) -> MediaInfo:
    path = Path(path)
    if ffprobe:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "stream=codec_type,width,height:format=duration",
             "-of", "json", "--", str(path)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            duration = float(data.get("format", {}).get("duration", 0) or 0)
            width = height = 0
            has_audio = False
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video" and not width:
                    width = int(stream.get("width") or 0)
                    height = int(stream.get("height") or 0)
                if stream.get("codec_type") == "audio":
                    has_audio = True
            if width and height:
                return MediaInfo(duration, width, height, has_audio)
    # Fallback: parse `ffmpeg -i` output (no ffprobe on this machine).
    result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)],
                            capture_output=True, text=True)
    text = result.stderr
    dm = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", text)
    duration = 0.0
    if dm:
        duration = int(dm[1]) * 3600 + int(dm[2]) * 60 + float(dm[3])
    vm = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", text)
    if not vm:
        raise RuntimeError(f"ابعاد ویدیو مشخص نشد: {path}")
    return MediaInfo(duration, int(vm[1]), int(vm[2]), "Audio:" in text)


def output_dimensions(info: MediaInfo, output_mode: str) -> tuple[int, int]:
    if output_mode == "original":
        return info.width, info.height
    if output_mode == "vertical":
        return 1080, 1920
    if output_mode == "horizontal":
        return 1920, 1080
    raise ValueError(f"Unknown output_mode {output_mode!r}; choose one of {OUTPUT_MODES}")


def _filter_path(path: str | Path) -> str:
    """Escape a path for use inside an ffmpeg filtergraph value."""
    p = str(Path(path).resolve()).replace("\\", "/")
    p = p.replace(":", r"\:").replace("'", r"\'").replace(",", r"\,")
    return f"'{p}'"


def build_filtergraph(
    ass_path: Path, font_dir: Path | None, info: MediaInfo, output_mode: str
) -> str:
    ass = f"ass={_filter_path(ass_path)}"
    if font_dir is not None:
        ass += f":fontsdir={_filter_path(font_dir)}"
    if output_mode == "original":
        return f"[0:v]{ass}[vout]"
    out_w, out_h = output_dimensions(info, output_mode)
    return (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h},boxblur=20:5[bg];"
        f"[fg]scale={out_w}:-2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{ass}[vout]"
    )


def extract_audio(video: Path, wav_out: Path, ffmpeg: str) -> Path:
    wav_out.parent.mkdir(parents=True, exist_ok=True)
    _run([ffmpeg, "-hide_banner", "-y", "-i", str(video),
          "-vn", "-ac", "1", "-ar", "16000", str(wav_out)])
    return wav_out


_SILENCE_START_RE = re.compile(r"silence_start:\s*([\d.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*([\d.]+)")


def parse_silencedetect(stderr_text: str) -> list[tuple[float, float]]:
    """Parse ffmpeg silencedetect log lines into (start, end) pairs."""
    silences: list[tuple[float, float]] = []
    pending: float | None = None
    for line in stderr_text.splitlines():
        start_match = _SILENCE_START_RE.search(line)
        if start_match:
            pending = float(start_match[1])
            continue
        end_match = _SILENCE_END_RE.search(line)
        if end_match and pending is not None:
            end = float(end_match[1])
            if end > pending:
                silences.append((pending, end))
            pending = None
    return silences


def detect_silences(
    media_path: str | Path,
    ffmpeg: str,
    noise_db: float = -35.0,
    min_silence: float = 0.6,
) -> list[tuple[float, float]]:
    """Return real audio silences via ffmpeg's silencedetect filter.

    Runs an audio-only decode pass, so it stays fast even on long videos.
    Background music can mask dialogue pauses; callers should combine this
    with subtitle-gap pauses (see cuts.find_candidates).
    """
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(media_path), "-vn",
         "-af", f"silencedetect=noise={noise_db:g}dB:d={min_silence:g}",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        tail = "\n".join((result.stderr or "").strip().splitlines()[-10:])
        raise RuntimeError(f"تشخیص سکوت با ffmpeg ناموفق بود:\n{tail}")
    return parse_silencedetect(result.stderr or "")


def render(
    video: Path,
    out: Path,
    ass_path: Path,
    info: MediaInfo,
    *,
    ffmpeg: str,
    font_dir: Path | None,
    output_mode: str = "original",
    start: float | None = None,
    duration: float | None = None,
    video_codec: str = "libx264",
    crf: int = 20,
    preset: str = "medium",
    audio_codec: str = "aac",
    audio_bitrate: str = "160k",
) -> Path:
    """Burn an ASS file into a (optionally trimmed) copy of the video.

    When start/duration are given, input seeking is used, so the ASS file
    must already be time-shifted to begin at 0 (see srt_io.clip_entries).
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd: list[str] = [ffmpeg, "-hide_banner", "-y"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-i", str(video), "-filter_complex",
            build_filtergraph(ass_path, font_dir, info, output_mode),
            "-map", "[vout]"]
    if info.has_audio:
        cmd += ["-map", "0:a:0", "-c:a", audio_codec, "-b:a", audio_bitrate]
    cmd += ["-c:v", video_codec, "-crf", str(crf), "-preset", preset,
            "-movflags", "+faststart", str(out)]
    _run(cmd)
    return out
