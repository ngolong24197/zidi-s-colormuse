"""Photo processing: validation, optimisation, cropping and color extraction.

Background reduction is heuristic (border-color masking + OpenCV GrabCut
initialised from the selected region). It is *not* a trained segmentation
model, so the UI always lets the owner crop and correct colors manually.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from src.core.color_convert import rgb_to_hex
from src.core.color_library import color_name, nearest_colors
from src.i18n import _

ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000  # decompression-bomb guard
MIN_SIDE = 64
FULL_MAX_SIDE = 1280
THUMB_MAX_SIDE = 360
JPEG_QUALITY = 84
THUMB_QUALITY = 78


class ImageValidationError(ValueError):
    """The uploaded file is not an acceptable image."""


@dataclass
class ProcessedImage:
    full: bytes
    thumb: bytes
    width: int
    height: int
    content_type: str = "image/jpeg"

    @property
    def size_bytes(self) -> int:
        return len(self.full)


@dataclass
class ExtractedColor:
    hex: str
    name: str
    share: float  # 0..1 of clothing pixels
    library_hex: str
    distance: float


@dataclass
class ExtractionResult:
    colors: list[ExtractedColor]
    mask_coverage: float  # share of the region kept as "clothing"
    method: str

    @property
    def primary(self) -> ExtractedColor | None:
        return self.colors[0] if self.colors else None

    @property
    def secondary(self) -> list[ExtractedColor]:
        return [c for c in self.colors[1:] if c.share >= 0.08]


# ---------------------------------------------------------------- validation

def validate_image(data: bytes, filename: str | None = None) -> Image.Image:
    """Validate size, extension, real format and dimensions. Returns an opened image."""
    if not data:
        raise ImageValidationError(_("The file is empty."))
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageValidationError(_("The photo is {size} MB; the limit is {limit} MB.",
                                     size=f"{len(data) / 1_048_576:.1f}", limit=MAX_UPLOAD_BYTES // 1_048_576))
    if filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise ImageValidationError(_("Please upload a JPG, PNG or WEBP photo."))
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format
        w, h = probe.size
        probe.verify()  # detects truncated / corrupt files
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ImageValidationError(_("This file is not a readable image.")) from exc
    if fmt not in ALLOWED_FORMATS:
        raise ImageValidationError(_("Unsupported image format ({fmt}). Use JPG, PNG or WEBP.", fmt=fmt))
    if w * h > MAX_PIXELS:
        raise ImageValidationError(_("The image dimensions are too large."))
    if min(w, h) < MIN_SIDE:
        raise ImageValidationError(_("The image is too small (minimum {px}px per side).", px=MIN_SIDE))
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


def to_rgb(img: Image.Image) -> Image.Image:
    """Apply EXIF orientation and flatten transparency onto ivory."""
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (248, 244, 239, 255))
        bg.alpha_composite(img)
        return bg.convert("RGB")
    return img.convert("RGB")


def crop_fraction(img: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    """Crop with a (left, top, right, bottom) box given as fractions 0..1."""
    left, top, right, bottom = box
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ValueError("Invalid crop box")
    w, h = img.size
    px = (int(round(left * w)), int(round(top * h)), int(round(right * w)), int(round(bottom * h)))
    if px[2] - px[0] < 8 or px[3] - px[1] < 8:
        raise ValueError("Crop area is too small")
    return img.crop(px)


def _encode_jpeg(img: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def optimize(img: Image.Image) -> ProcessedImage:
    """Resize + JPEG-compress for storage, and make a thumbnail. Strips metadata."""
    rgb = to_rgb(img)
    full = rgb.copy()
    full.thumbnail((FULL_MAX_SIDE, FULL_MAX_SIDE), Image.Resampling.LANCZOS)
    thumb = rgb.copy()
    thumb.thumbnail((THUMB_MAX_SIDE, THUMB_MAX_SIDE), Image.Resampling.LANCZOS)
    return ProcessedImage(
        full=_encode_jpeg(full, JPEG_QUALITY),
        thumb=_encode_jpeg(thumb, THUMB_QUALITY),
        width=full.width,
        height=full.height,
    )


def process_upload(data: bytes, filename: str | None = None, crop: tuple[float, float, float, float] | None = None) -> ProcessedImage:
    img = validate_image(data, filename)
    img = to_rgb(img)
    if crop and crop != (0.0, 0.0, 1.0, 1.0):
        img = crop_fraction(img, crop)
    return optimize(img)


def preview_with_box(img: Image.Image, box: tuple[float, float, float, float], max_side: int = 640) -> Image.Image:
    """Preview of the selection: area outside the box is dimmed."""
    from PIL import ImageDraw

    base = to_rgb(img)
    base.thumbnail((max_side, max_side))
    w, h = base.size
    l, t, r, b = (int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h))
    dim = Image.new("RGBA", base.size, (48, 43, 43, 140))
    hole = Image.new("L", base.size, 255)
    ImageDraw.Draw(hole).rectangle((l, t, r, b), fill=0)
    out = base.convert("RGBA")
    out.paste(dim, (0, 0), hole)
    ImageDraw.Draw(out).rectangle((l, t, r, b), outline=(183, 126, 121, 255), width=3)
    return out.convert("RGB")


# ---------------------------------------------------------------- color extraction

def _work_array(img: Image.Image, side: int = 220) -> np.ndarray:
    small = to_rgb(img).copy()
    small.thumbnail((side, side), Image.Resampling.BILINEAR)
    return np.asarray(small, dtype=np.uint8)


def _border_mask(rgb: np.ndarray, threshold: float = 14.0) -> np.ndarray:
    """True where a pixel differs from the dominant border (background) colors."""
    from skimage.color import deltaE_ciede2000, rgb2lab

    lab = rgb2lab(rgb)
    h, w = rgb.shape[:2]
    bw = max(2, min(h, w) // 25)
    border = np.concatenate([lab[:bw].reshape(-1, 3), lab[-bw:].reshape(-1, 3),
                             lab[:, :bw].reshape(-1, 3), lab[:, -bw:].reshape(-1, 3)])
    # up to 3 background colors from the border
    data = border.astype(np.float32)
    k = 3 if len(data) >= 30 else 1
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    _compactness, labels, centers = cv2.kmeans(data, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k)
    keep = np.ones((h, w), dtype=bool)
    for idx in range(k):
        if counts[idx] / len(data) < 0.15:
            continue  # border pixels belonging to the garment itself
        de = deltaE_ciede2000(lab, np.broadcast_to(centers[idx], lab.shape))
        keep &= de > threshold
    return keep


def _grabcut_mask(rgb: np.ndarray) -> np.ndarray | None:
    h, w = rgb.shape[:2]
    if min(h, w) < 40:
        return None
    mask = np.zeros((h, w), np.uint8)
    rect = (max(1, w // 20), max(1, h // 20), w - 2 * max(1, w // 20), h - 2 * max(1, h // 20))
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), mask, rect, bgd, fgd, 3, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        return None
    return (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)


def clothing_mask(rgb: np.ndarray, reduce_background: bool = True) -> tuple[np.ndarray, str]:
    """Best-effort foreground mask. Falls back to the full region when unsure."""
    h, w = rgb.shape[:2]
    full = np.ones((h, w), dtype=bool)
    if not reduce_background:
        return full, "full region"
    border = _border_mask(rgb)
    gc = _grabcut_mask(rgb)
    candidates = []
    if gc is not None:
        combined = gc & border
        candidates.append((combined, "grabcut + background color removal"))
        candidates.append((gc, "grabcut"))
    candidates.append((border, "background color removal"))
    for mask, method in candidates:
        cov = mask.mean()
        if 0.08 <= cov <= 0.97:
            cleaned = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
            if cleaned.mean() >= 0.05:
                return cleaned, method
    return full, "full region"


def extract_colors(
    img: Image.Image,
    crop: tuple[float, float, float, float] | None = None,
    k: int = 5,
    reduce_background: bool = True,
) -> ExtractionResult:
    """Dominant colors of the clothing region, matched to the color library."""
    from skimage.color import deltaE_ciede2000, lab2rgb, rgb2lab

    if crop and crop != (0.0, 0.0, 1.0, 1.0):
        img = crop_fraction(to_rgb(img), crop)
    rgb = _work_array(img)
    mask, method = clothing_mask(rgb, reduce_background)
    lab = rgb2lab(rgb)
    pixels = lab[mask].astype(np.float32)
    if len(pixels) < k:
        pixels = lab.reshape(-1, 3).astype(np.float32)
    k = max(1, min(k, len(pixels)))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.3)
    cv2.setRNGSeed(7)  # deterministic clustering
    _compactness, labels, centers = cv2.kmeans(pixels, k, None, criteria, 4, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k).astype(float)

    # merge perceptually similar clusters (ΔE2000 < 9)
    order = list(np.argsort(-counts))
    merged: list[tuple[np.ndarray, float]] = []
    for idx in order:
        c, n = centers[idx].astype(float), counts[idx]
        for j, (mc, mn) in enumerate(merged):
            if float(deltaE_ciede2000(mc, c)) < 9:
                merged[j] = ((mc * mn + c * n) / (mn + n), mn + n)
                break
        else:
            merged.append((c, n))
    total = sum(n for _center, n in merged) or 1.0
    merged.sort(key=lambda t: -t[1])

    colors: list[ExtractedColor] = []
    for c, n in merged:
        rgb_f = lab2rgb(np.asarray(c, dtype=float).reshape(1, 1, 3)).reshape(3)
        hx = rgb_to_hex(tuple(float(v) * 255 for v in rgb_f))
        near, dist = nearest_colors(hx, 1)[0]
        colors.append(ExtractedColor(hx, color_name(hx), round(n / total, 4), near.hex, round(dist, 2)))
    return ExtractionResult(colors, round(float(mask.mean()), 4), method)


def open_image(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    return img
