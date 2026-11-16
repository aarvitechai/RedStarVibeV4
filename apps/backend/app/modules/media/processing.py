"""Pure media processing (no DB). Never trusts the declared type: the bytes decide (Blueprint 12.3)."""

import io
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 60_000_000  # decompression-bomb guard
IMAGE_WIDTHS = (320, 640, 1080)
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "AVIF", "GIF", "MPO"}


class InvalidMedia(Exception):
    pass


@dataclass
class Rendition:
    name: str
    data: bytes
    content_type: str


@dataclass
class Processed:
    width: int
    height: int
    duration_s: float | None = None
    renditions: list[Rendition] = field(default_factory=list)


def process_image(data: bytes) -> Processed:
    """Validate by decoding, apply EXIF rotation, drop all metadata (incl. GPS), re-encode to WebP + AVIF sizes."""
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()
    except Exception as exc:
        raise InvalidMedia("not a valid image") from exc
    if fmt not in ALLOWED_IMAGE_FORMATS:
        raise InvalidMedia(f"unsupported image format {fmt}")
    with Image.open(io.BytesIO(data)) as img:
        img.seek(0)
        rgb = ImageOps.exif_transpose(img).convert("RGB")  # new image object: no EXIF/ICC/XMP carried over
    out = Processed(width=rgb.width, height=rgb.height)
    for width in IMAGE_WIDTHS:
        if width > rgb.width and width != IMAGE_WIDTHS[0]:
            continue
        scaled = (
            rgb if rgb.width <= width else rgb.resize((width, round(rgb.height * width / rgb.width)), Image.Resampling.LANCZOS)
        )
        for ext, mime, opts in (("webp", "image/webp", {"quality": 80, "method": 4}), ("avif", "image/avif", {"quality": 55})):
            buf = io.BytesIO()
            scaled.save(buf, format=ext.upper(), **opts)
            out.renditions.append(Rendition(f"{width}.{ext}", buf.getvalue(), mime))
    return out


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _probe(path: Path) -> dict[str, object]:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if res.returncode != 0:
        raise InvalidMedia("not a valid media file")
    data: dict[str, object] = json.loads(res.stdout)
    return data


def process_av(data: bytes, kind: str, max_duration_s: float) -> Processed:
    """Video -> H.264/AAC MP4 (max 720p) + JPEG poster. Audio (voice notes) -> AAC M4A. Metadata stripped."""
    if not ffmpeg_available():
        raise InvalidMedia("media processing unavailable")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        src.write_bytes(data)
        info = _probe(src)
        streams = info.get("streams") or []
        assert isinstance(streams, list)
        has_video = any(s.get("codec_type") == "video" for s in streams if isinstance(s, dict))
        if kind == "video" and not has_video:
            raise InvalidMedia("no video stream")
        fmt = info.get("format") or {}
        duration = float(fmt.get("duration", 0) if isinstance(fmt, dict) else 0)
        if duration <= 0 or duration > max_duration_s:
            raise InvalidMedia(f"duration must be between 1 and {int(max_duration_s)} seconds")
        out = Processed(width=0, height=0, duration_s=round(duration, 2))
        common = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-map_metadata", "-1"]
        if kind == "video":
            dst, poster = Path(tmp) / "v.mp4", Path(tmp) / "p.jpg"
            subprocess.run(
                [
                    *common,
                    "-vf",
                    "scale='min(1280,iw)':-2",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "26",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-movflags",
                    "+faststart",
                    str(dst),
                ],
                check=True,
                timeout=600,
            )
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", str(dst), "-frames:v", "1", str(poster)],
                check=True,
                timeout=60,
            )
            probed = _probe(dst).get("streams") or []
            assert isinstance(probed, list)
            vs = next(s for s in probed if isinstance(s, dict) and s.get("codec_type") == "video")
            out.width, out.height = int(vs["width"]), int(vs["height"])
            out.renditions += [
                Rendition("video.mp4", dst.read_bytes(), "video/mp4"),
                Rendition("poster.jpg", poster.read_bytes(), "image/jpeg"),
            ]
        else:
            dst = Path(tmp) / "a.m4a"
            subprocess.run([*common, "-vn", "-c:a", "aac", "-b:a", "64k", str(dst)], check=True, timeout=300)
            out.renditions.append(Rendition("audio.m4a", dst.read_bytes(), "audio/mp4"))
        return out
