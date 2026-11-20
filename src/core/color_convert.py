"""Color space conversions and perceptual distance.

Pure-Python scalar implementations (fast for the recommendation engine, which
works on a handful of colors at a time). Vectorised image work uses
scikit-image; the test-suite cross-checks both implementations.

Conventions:
    RGB  -> tuple of ints 0..255
    HSL  -> (h 0..360, s 0..1, l 0..1)
    HSV  -> (h 0..360, s 0..1, v 0..1)
    Lab  -> CIE L*a*b* (D65), L in 0..100
"""

from __future__ import annotations

import colorsys
import math
import re
from functools import lru_cache

RGB = tuple[int, int, int]
Triple = tuple[float, float, float]

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# D65 reference white
_XN, _YN, _ZN = 0.95047, 1.0, 1.08883


class ColorError(ValueError):
    """Raised for malformed color input."""


def normalize_hex(value: str) -> str:
    """Return a canonical ``#RRGGBB`` upper-case string."""
    if not isinstance(value, str):
        raise ColorError(f"Color must be a hex string, got {type(value).__name__}")
    m = _HEX_RE.match(value.strip())
    if not m:
        raise ColorError(f"Invalid hex color: {value!r}")
    digits = m.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return "#" + digits.upper()


def is_valid_hex(value: object) -> bool:
    return isinstance(value, str) and bool(_HEX_RE.match(value.strip()))


def hex_to_rgb(value: str) -> RGB:
    h = normalize_hex(value)[1:]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    r, g, b = (int(round(max(0, min(255, c)))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def rgb_to_hsl(rgb: RGB) -> Triple:
    r, g, b = (c / 255.0 for c in rgb)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360.0, s, l


def hsl_to_rgb(hsl: Triple) -> RGB:
    h, s, l = hsl
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, _clamp01(l), _clamp01(s))
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def rgb_to_hsv(rgb: RGB) -> Triple:
    r, g, b = (c / 255.0 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360.0, s, v


def hsv_to_rgb(hsv: Triple) -> RGB:
    h, s, v = hsv
    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, _clamp01(s), _clamp01(v))
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def hex_to_hsl(value: str) -> Triple:
    return rgb_to_hsl(hex_to_rgb(value))


def hsl_to_hex(hsl: Triple) -> str:
    return rgb_to_hex(hsl_to_rgb(hsl))


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def rgb_to_xyz(rgb: RGB) -> Triple:
    r, g, b = (_srgb_to_linear(c / 255.0) for c in rgb)
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b
    return x, y, z


def _f(t: float) -> float:
    d = 6 / 29
    return t ** (1 / 3) if t > d**3 else t / (3 * d * d) + 4 / 29


def _finv(t: float) -> float:
    d = 6 / 29
    return t**3 if t > d else 3 * d * d * (t - 4 / 29)


def rgb_to_lab(rgb: RGB) -> Triple:
    x, y, z = rgb_to_xyz(rgb)
    fx, fy, fz = _f(x / _XN), _f(y / _YN), _f(z / _ZN)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def lab_to_rgb(lab: Triple) -> RGB:
    L, a, b = lab
    fy = (L + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200
    x, y, z = _XN * _finv(fx), _YN * _finv(fy), _ZN * _finv(fz)
    r = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    g = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    bb = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z
    return tuple(int(round(_clamp01(_linear_to_srgb(_clamp01(c))) * 255)) for c in (r, g, bb))  # type: ignore[return-value]


@lru_cache(maxsize=8192)
def hex_to_lab(value: str) -> Triple:
    return rgb_to_lab(hex_to_rgb(value))


def lab_to_lch(lab: Triple) -> Triple:
    L, a, b = lab
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def delta_e_76(lab1: Triple, lab2: Triple) -> float:
    return math.dist(lab1, lab2)


def delta_e_2000(lab1: Triple, lab2: Triple) -> float:
    """CIEDE2000 color difference (Sharma, Wu & Dalal 2005)."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cbar**7 / (Cbar**7 + 25**7))) if Cbar > 0 else 0.0
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if (a1p or b1) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if (a2p or b2) else 0.0

    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    else:
        dhp = h2p - h1p
        if dhp > 180:
            dhp -= 360
        elif dhp < -180:
            dhp += 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))

    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbp = (h1p + h2p + 360) / 2
    else:
        hbp = (h1p + h2p - 360) / 2

    T = (
        1
        - 0.17 * math.cos(math.radians(hbp - 30))
        + 0.24 * math.cos(math.radians(2 * hbp))
        + 0.32 * math.cos(math.radians(3 * hbp + 6))
        - 0.20 * math.cos(math.radians(4 * hbp - 63))
    )
    d_theta = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cbp**7 / (Cbp**7 + 25**7)) if Cbp > 0 else 0.0
    Sl = 1 + (0.015 * (Lbp - 50) ** 2) / math.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -math.sin(math.radians(2 * d_theta)) * Rc
    return math.sqrt(
        (dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh)
    )


def color_distance(hex1: str, hex2: str) -> float:
    """Perceptual distance (CIEDE2000) between two hex colors."""
    return delta_e_2000(hex_to_lab(hex1), hex_to_lab(hex2))


def relative_luminance(rgb: RGB) -> float:
    r, g, b = (_srgb_to_linear(c / 255.0) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex1: str, hex2: str) -> float:
    """WCAG contrast ratio, 1..21."""
    l1 = relative_luminance(hex_to_rgb(hex1))
    l2 = relative_luminance(hex_to_rgb(hex2))
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def hue_difference(h1: float, h2: float) -> float:
    """Smallest angle between two hues, 0..180."""
    d = abs(h1 - h2) % 360
    return 360 - d if d > 180 else d


def chroma(hex_value: str) -> float:
    """CIE LCh chroma — perceptual colorfulness (0 = gray)."""
    return lab_to_lch(hex_to_lab(hex_value))[1]


def lightness(hex_value: str) -> float:
    """CIE L* lightness 0..100."""
    return hex_to_lab(hex_value)[0]


def shade_of(hex_value: str) -> str:
    """Classify a color as 'light', 'medium' or 'dark' by perceptual lightness."""
    L = lightness(hex_value)
    if L >= 70:
        return "light"
    if L >= 40:
        return "medium"
    return "dark"


def adjust_lightness(hex_value: str, delta: float) -> str:
    """Shift HSL lightness by ``delta`` (−1..1), clamped."""
    h, s, l = hex_to_hsl(hex_value)
    return hsl_to_hex((h, s, _clamp01(l + delta)))


def mix(hex1: str, hex2: str, t: float) -> str:
    """Linear sRGB mix; t=0 → hex1, t=1 → hex2."""
    a, b = hex_to_rgb(hex1), hex_to_rgb(hex2)
    return rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))  # type: ignore[arg-type]


def text_color_for(background_hex: str) -> str:
    """Charcoal or ivory text, whichever has more contrast on the background."""
    dark, light = "#302B2B", "#F8F4EF"
    return dark if contrast_ratio(background_hex, dark) >= contrast_ratio(background_hex, light) else light
