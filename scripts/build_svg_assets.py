"""Generate the reusable SVG assets for the mannequin and garment templates.

Run:  python scripts/build_svg_assets.py

All assets share one 400x1000 coordinate space (the croquis figure), so every
garment layer lines up on the mannequin, and the flat-lay renderer simply crops
each layer to its own bounding box.

Path classes understood by src/visualizer/svg_assets.py:
    skin, hair      body colors (owner-configurable)
    fill            main garment color (patterns applied here)
    shade           darker tone of the main color
    accent          secondary color (buttons, trims)
    metal           hardware (buckles, clasps)
    sole            shoe soles / French-tip white
    dark            fixed charcoal (polish bottle caps)
    line            interior detail stroke (darker main color)
    strap           thick stroke in the main color (bag handles, straps)
Shapes use only M/L/C/Z commands and never contain holes.
"""

from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CX = 200.0

Pt = tuple  # (x, y) smooth point or (x, y, "s") sharp corner


def _xy(p):
    return float(p[0]), float(p[1])


def _sharp(p) -> bool:
    return len(p) > 2 and p[2] == "s"


def smooth_closed(points: list, tension: float = 1.0) -> str:
    """Closed Catmull-Rom spline through points, with optional sharp corners."""
    n = len(points)
    d = [f"M{points[0][0]:.1f},{points[0][1]:.1f}"]
    for i in range(n):
        p0, p1, p2, p3 = points[i - 1], points[i], points[(i + 1) % n], points[(i + 2) % n]
        x0, y0 = _xy(p0)
        x1, y1 = _xy(p1)
        x2, y2 = _xy(p2)
        x3, y3 = _xy(p3)
        if _sharp(p1):
            c1 = (x1, y1)
        else:
            c1 = (x1 + (x2 - x0) / 6 * tension, y1 + (y2 - y0) / 6 * tension)
        if _sharp(p2):
            c2 = (x2, y2)
        else:
            c2 = (x2 - (x3 - x1) / 6 * tension, y2 - (y3 - y1) / 6 * tension)
        d.append(f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {x2:.1f},{y2:.1f}")
    d.append("Z")
    return " ".join(d)


def poly(points: list) -> str:
    return "M" + " L".join(f"{_xy(p)[0]:.1f},{_xy(p)[1]:.1f}" for p in points) + " Z"


def polyline(points: list) -> str:
    return "M" + " L".join(f"{_xy(p)[0]:.1f},{_xy(p)[1]:.1f}" for p in points)


def curve(p0, c1, c2, p1) -> str:
    return f"M{p0[0]:.1f},{p0[1]:.1f} C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p1[0]:.1f},{p1[1]:.1f}"


def mirror_pt(p):
    x, y = _xy(p)
    return (2 * CX - x, y) + (("s",) if _sharp(p) else ())


def sym(left: list) -> list:
    """Left half (top-centre → down the left side → bottom-centre) to a full outline."""
    right = [mirror_pt(p) for p in reversed(left) if abs(_xy(p)[0] - CX) > 0.01]
    return list(left) + right


def mirror_points(points: list) -> list:
    return [mirror_pt(p) for p in points]


def mirror_d(d: str) -> str:
    """Mirror an M/L/C path string across x = CX."""
    # numbers come in x,y pairs, optionally prefixed by a command letter
    res, toks = [], d.split()
    for t in toks:
        cmd = ""
        if t[0].isalpha():
            cmd, t = t[0], t[1:]
        if not t:
            res.append(cmd)
            continue
        x, y = t.split(",")
        res.append(f"{cmd}{2 * CX - float(x):.1f},{float(y):.1f}")
    return " ".join(res)


def ellipse(cx, cy, rx, ry) -> str:
    k = 0.5523
    return (
        f"M{cx - rx:.1f},{cy:.1f} "
        f"C{cx - rx:.1f},{cy - ry * k:.1f} {cx - rx * k:.1f},{cy - ry:.1f} {cx:.1f},{cy - ry:.1f} "
        f"C{cx + rx * k:.1f},{cy - ry:.1f} {cx + rx:.1f},{cy - ry * k:.1f} {cx + rx:.1f},{cy:.1f} "
        f"C{cx + rx:.1f},{cy + ry * k:.1f} {cx + rx * k:.1f},{cy + ry:.1f} {cx:.1f},{cy + ry:.1f} "
        f"C{cx - rx * k:.1f},{cy + ry:.1f} {cx - rx:.1f},{cy + ry * k:.1f} {cx - rx:.1f},{cy:.1f} Z"
    )


def rotated_ellipse_pts(cx, cy, rx, ry, angle_deg, n=16):
    a = math.radians(angle_deg)
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append((cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)))
    return pts


def both(d_left: str) -> list[str]:
    return [d_left, mirror_d(d_left)]


# ---------------------------------------------------------------- body

ARM_LEFT = [
    (131, 182), (122, 196), (117, 240), (114, 290), (112, 330), (110, 380), (107, 430), (106, 452),
    (101, 470), (98, 492), (100, 510), (106, 518), (113, 512), (117, 494), (121, 470), (122, 452),
    (127, 400), (131, 330), (136, 280), (140, 240),
]

TORSO_LEFT = [
    (200, 124), (189, 124, "s"), (188, 152), (180, 162), (160, 168), (140, 174), (130, 186), (131, 206),
    (138, 236), (146, 280), (156, 326), (152, 370), (144, 412), (145, 452), (152, 520), (160, 600),
    (166, 676), (166, 710), (171, 770), (178, 850), (181, 898), (179, 920), (175, 944), (178, 958),
    (190, 962), (197, 955), (196, 930), (192, 900), (190, 850), (188, 770), (190, 700), (191, 676),
    (194, 600), (197, 520), (199, 482, "s"), (200, 478),
]


def body_layers() -> dict[str, list[tuple[str, str]]]:
    arms = [("skin", smooth_closed(ARM_LEFT)), ("skin", smooth_closed(mirror_points(ARM_LEFT)))]
    torso = [("skin", smooth_closed(sym(TORSO_LEFT)))]
    head = [("skin", ellipse(200, 88, 31, 41))]
    return {"body": arms + torso + head}


# Sleek cap that covers the top of the head (used by up-dos and short styles)
_CAP = [(168, 98, "s"), (167, 72), (177, 54), (200, 44), (223, 54), (233, 72), (232, 98, "s"),
        (226, 80), (212, 66), (200, 63), (188, 66), (174, 80)]
_PART = polyline([(200, 45), (204, 62)])
_SWEPT_FRONT = [(169, 98, "s"), (167, 72), (176, 54), (194, 44), (214, 45), (229, 56), (235, 78),
                (234, 106, "s"), (227, 86), (214, 68), (196, 62), (183, 72), (175, 100, "s")]


def hair_styles() -> dict[str, dict[str, list[tuple[str, str]]]]:
    """Each style has a 'back' layer (behind the body) and a 'front' layer (over the head)."""
    long_back = [(200, 40), (176, 46), (161, 66), (156, 100), (155, 150), (158, 196), (168, 216),
                 (184, 206), (200, 200)]
    bob_back = [(200, 40), (174, 46), (160, 68), (157, 104), (160, 136), (170, 146, "s"), (186, 140), (200, 138)]
    curly_back = [(200, 30), (172, 34), (150, 52), (140, 84), (138, 120), (142, 160), (150, 196), (164, 216),
                  (184, 206), (200, 200)]
    pony_tail = smooth_closed([(222, 60), (238, 76), (244, 118), (240, 170), (232, 214), (226, 222, "s"),
                               (226, 180), (230, 130), (226, 90), (216, 70)])
    braid = [("hair", ellipse(162 - n * 0.5, 130 + n * 17, 9 - n * 0.4, 10)) for n in range(7)]
    braid_lines = [("line", polyline([(156 - n * 0.5, 126 + n * 17), (168 - n * 0.5, 136 + n * 17)])) for n in range(7)]
    curls = [("hair", ellipse(x, y, r, r)) for x, y, r in
             [(176, 50, 16), (200, 40, 17), (224, 50, 16), (166, 72, 12), (234, 72, 12)]]
    return {
        "long_waves": {"back": [("hair", smooth_closed(sym(long_back)))],
                       "front": [("hair", smooth_closed(_SWEPT_FRONT))]},
        "bob": {"back": [("hair", smooth_closed(sym(bob_back)))],
                "front": [("hair", smooth_closed([(166, 120, "s"), (165, 76), (176, 54), (200, 44), (224, 54), (235, 76),
                                                  (234, 120, "s"), (228, 92), (216, 70), (200, 64), (184, 70), (172, 92)])),
                          ("line", _PART)]},
        "ponytail": {"back": [("hair", pony_tail)],
                     "front": [("hair", smooth_closed(_CAP)), ("line", _PART),
                               ("shade", ellipse(222, 62, 5, 4))]},
        "bun": {"back": [("hair", ellipse(200, 34, 19, 15))],
                "front": [("hair", smooth_closed(_CAP)), ("line", _PART),
                          ("line", curve((184, 30), (192, 22), (208, 22), (216, 30)))]},
        "curly": {"back": [("hair", smooth_closed(sym(curly_back)))],
                  "front": curls},
        "pixie": {"back": [],
                  "front": [("hair", smooth_closed([(168, 104, "s"), (165, 72), (176, 52), (198, 42), (220, 46), (233, 60),
                                                    (235, 84), (233, 100, "s"), (226, 78), (208, 70), (190, 76), (176, 92)]))]},
        "side_braid": {"back": [("hair", smooth_closed(sym([(200, 40), (176, 46), (163, 66), (160, 100), (166, 126), (200, 124)])))],
                       "front": [("hair", smooth_closed(_SWEPT_FRONT))] + braid + braid_lines},
    }


NAIL_TIPS = [(103, 512), (108, 517), (113, 513)]
NAIL_SHAPES = ("almond", "round", "square", "french")


def _nail(cx: float, cy: float, shape: str, k: float = 1.0) -> list[tuple[str, str]]:
    w, h = 2.2 * k, 3.4 * k
    if shape == "almond":
        d = smooth_closed([(cx - w, cy - h * 0.4), (cx, cy - h * 0.6), (cx + w, cy - h * 0.4),
                           (cx + w * 0.6, cy + h * 0.5), (cx, cy + h * 1.2, "s"), (cx - w * 0.6, cy + h * 0.5)])
        return [("fill", d)]
    if shape == "square":
        return [("fill", poly([(cx - w, cy - h * 0.6), (cx + w, cy - h * 0.6), (cx + w, cy + h * 0.8), (cx - w, cy + h * 0.8)]))]
    base = [("fill", ellipse(cx, cy, w, h))]
    if shape == "french":
        base.append(("sole", smooth_closed([(cx - w * 0.95, cy + h * 0.35, "s"), (cx, cy + h * 0.15),
                                             (cx + w * 0.95, cy + h * 0.35, "s"), (cx, cy + h)])))
    return base


def mannequin_nails() -> dict[str, list[tuple[str, str]]]:
    out = {}
    for shape in NAIL_SHAPES:
        paths: list[tuple[str, str]] = []
        for x, y in NAIL_TIPS:
            paths += _nail(x, y, shape)
            paths += [(cls, mirror_d(d)) for cls, d in _nail(x, y, shape)]
        out[f"nails_{shape}"] = paths
    return out


def nail_templates() -> dict[str, list[tuple[str, str]]]:
    """Flat-lay card: a polish bottle and five large nails of the chosen shape."""
    out = {}
    bottle = [("dark", smooth_closed([(232, 40, "s"), (252, 40, "s"), (254, 92, "s"), (230, 92, "s")])),
              ("fill", smooth_closed([(222, 96), (262, 96), (270, 120), (268, 170, "s"), (216, 170, "s"), (214, 120)])),
              ("shade", poly([(228, 108), (234, 108), (232, 160), (226, 160)]))]
    for shape in NAIL_SHAPES:
        paths = list(bottle)
        for x, y in [(110, 120), (132, 104), (154, 100), (176, 108), (130, 160)]:
            paths += _nail(x, y, shape, k=-4.2)  # flipped: tips point up on the card
        out[f"nails_{shape}"] = paths
    return out


# ---------------------------------------------------------------- garments

def tops() -> dict[str, list[tuple[str, str]]]:
    tee = [(200, 174), (190, 170), (184, 160, "s"), (160, 166), (138, 173), (127, 186), (118, 214),
           (110, 258, "s"), (141, 264, "s"), (144, 240), (147, 282), (153, 328), (152, 372),
           (150, 410, "s"), (200, 414)]
    blouse = [(200, 215, "s"), (186, 168, "s"), (160, 167), (138, 174), (127, 187), (117, 240),
              (112, 330), (108, 420), (104, 452, "s"), (125, 458, "s"), (129, 400), (134, 330),
              (139, 270), (144, 240), (148, 282), (155, 328), (153, 372), (151, 402, "s"), (200, 406)]
    sweater = [(200, 172), (189, 168), (182, 159, "s"), (160, 165), (137, 173), (126, 186), (114, 240),
               (108, 330), (103, 430), (101, 456, "s"), (127, 462, "s"), (131, 400), (136, 330),
               (140, 270), (145, 242), (150, 284), (156, 330), (156, 380), (154, 424, "s"), (200, 426)]
    tank = [(200, 206), (188, 200), (180, 186), (178, 172, "s"), (168, 170, "s"), (162, 190), (152, 214),
            (146, 240), (149, 282), (155, 328), (153, 372), (151, 408, "s"), (200, 410)]
    return {
        "tee": [("fill", smooth_closed(sym(tee))),
                ("line", polyline([(113, 246), (142, 252)])), ("line", mirror_d(polyline([(113, 246), (142, 252)])))],
        "blouse": [("fill", smooth_closed(sym(blouse))),
                   ("shade", poly([(105, 440), (126, 446), (125, 458), (104, 452)])),
                   ("shade", mirror_d(poly([(105, 440), (126, 446), (125, 458), (104, 452)]))),
                   ("line", polyline([(200, 216), (200, 404)])),
                   ("accent", ellipse(200, 244, 3, 3)), ("accent", ellipse(200, 284, 3, 3)),
                   ("accent", ellipse(200, 324, 3, 3)), ("accent", ellipse(200, 364, 3, 3))],
        "sweater": [("fill", smooth_closed(sym(sweater))),
                    ("shade", smooth_closed(sym([(200, 404), (155, 404, "s"), (154, 424, "s"), (200, 426)]))),
                    ("shade", poly([(102, 440), (129, 446), (127, 462), (101, 456)])),
                    ("shade", mirror_d(poly([(102, 440), (129, 446), (127, 462), (101, 456)]))),
                    ("shade", smooth_closed(sym([(200, 172), (189, 168), (182, 159, "s"), (186, 158, "s"), (192, 164), (200, 166)])))],
        "tank": [("fill", smooth_closed(sym(tank)))],
    }


def bottoms() -> dict[str, list[tuple[str, str]]]:
    waist = [(200, 322, "s"), (157, 322, "s")]
    band = ("shade", poly([(157, 322), (156.5, 336), (243.5, 336), (243, 322)]))
    pants = waist + [(152, 370), (146, 412), (148, 460), (153, 540), (158, 620), (161, 700), (164, 800),
                     (166, 905, "s"), (195, 905, "s"), (194, 800), (194, 700), (196, 600), (198, 520),
                     (199, 486, "s"), (200, 486)]
    shorts = waist + [(152, 370), (146, 412), (147, 470), (150, 540, "s"), (197, 540, "s"), (198, 510),
                      (199, 486, "s"), (200, 486)]
    mini = waist + [(151, 370), (143, 420), (132, 520, "s"), (200, 526)]
    midi = waist + [(151, 370), (143, 420), (133, 520), (122, 640), (116, 700, "s"), (200, 708)]
    maxi = waist + [(151, 370), (143, 420), (130, 560), (118, 760), (108, 905, "s"), (200, 912)]
    crease = polyline([(176, 480), (180, 900)])
    return {
        "pants": [("fill", smooth_closed(sym(pants))), band, ("line", crease), ("line", mirror_d(crease)),
                  ("line", polyline([(200, 336), (200, 420)]))],
        "shorts": [("fill", smooth_closed(sym(shorts))), band, ("line", polyline([(200, 336), (200, 420)]))],
        "skirt_mini": [("fill", smooth_closed(sym(mini))), band,
                       ("line", polyline([(178, 360), (170, 520)])), ("line", mirror_d(polyline([(178, 360), (170, 520)])))],
        "skirt_midi": [("fill", smooth_closed(sym(midi))), band,
                       ("line", polyline([(178, 360), (165, 700)])), ("line", mirror_d(polyline([(178, 360), (165, 700)]))),
                       ("line", polyline([(200, 380), (200, 706)]))],
        "skirt_maxi": [("fill", smooth_closed(sym(maxi))), band,
                       ("line", polyline([(178, 360), (160, 905)])), ("line", mirror_d(polyline([(178, 360), (160, 905)]))),
                       ("line", polyline([(200, 380), (200, 910)]))],
    }


def dresses() -> dict[str, list[tuple[str, str]]]:
    bodice = [(200, 212, "s"), (186, 170, "s"), (170, 168, "s"), (160, 192), (150, 220), (146, 242),
              (149, 284), (156, 328)]
    seam = ("shade", poly([(156.5, 322), (156, 334), (244, 334), (243.5, 322)]))
    mini = bodice + [(150, 372), (142, 420), (134, 520, "s"), (200, 524)]
    midi = bodice + [(150, 372), (142, 420), (130, 540), (120, 700, "s"), (200, 708)]
    maxi = bodice + [(150, 372), (142, 420), (128, 580), (112, 905, "s"), (200, 912)]
    def drape(y_end, x_end):
        d = polyline([(180, 345), (x_end, y_end)])
        return [("line", d), ("line", mirror_d(d))]
    return {
        "dress_mini": [("fill", smooth_closed(sym(mini))), seam] + drape(515, 168),
        "dress_midi": [("fill", smooth_closed(sym(midi))), seam] + drape(700, 160) + [("line", polyline([(200, 360), (200, 706)]))],
        "dress_maxi": [("fill", smooth_closed(sym(maxi))), seam] + drape(905, 152) + [("line", polyline([(200, 360), (200, 910)]))],
    }


def outerwear() -> dict[str, list[tuple[str, str]]]:
    sleeve_and_side = [(127, 187), (117, 240), (112, 330), (107, 420), (103, 452, "s"), (126, 458, "s"),
                       (130, 400), (135, 330), (140, 270), (145, 244)]
    blazer = [(186, 160, "s"), (160, 166), (137, 174)] + sleeve_and_side + [
        (149, 290), (152, 340), (150, 400), (149, 452, "s"), (191, 456, "s"), (190, 330, "s"), (178, 240), (177, 192)]
    coat = [(186, 158, "s"), (160, 165), (136, 173)] + [(126, 187), (115, 240), (110, 330), (105, 420), (101, 462, "s"),
            (128, 468, "s"), (131, 400), (136, 330), (141, 270), (146, 244)] + [
        (150, 290), (154, 340), (152, 420), (147, 520), (141, 650, "s"), (193, 656, "s"), (191, 330, "s"), (176, 236), (175, 190)]
    cardigan = [(184, 160, "s"), (160, 166), (137, 174)] + sleeve_and_side + [
        (149, 290), (152, 340), (151, 400), (150, 446, "s"), (193, 450, "s"), (192, 300), (188, 220)]
    lapel = poly([(178, 176), (160, 196), (170, 228), (190, 328), (180, 240)])
    coat_lapel = poly([(176, 172), (154, 196), (166, 232), (191, 328), (178, 236)])
    pocket = polyline([(156, 410), (180, 412)])
    coat_belt = poly([(152, 330), (152, 344), (192, 344), (192, 330)])
    rib = poly([(150, 436), (193, 438), (193, 450), (150, 446)])
    out = {
        "blazer": [("fill", smooth_closed(blazer)), ("fill", mirror_d(smooth_closed(blazer))),
                   ("shade", lapel), ("shade", mirror_d(lapel)),
                   ("line", pocket), ("line", mirror_d(pocket)),
                   ("accent", ellipse(194, 372, 4, 4)), ("accent", ellipse(194, 410, 4, 4))],
        "coat": [("fill", smooth_closed(coat)), ("fill", mirror_d(smooth_closed(coat))),
                 ("shade", coat_lapel), ("shade", mirror_d(coat_lapel)),
                 ("shade", coat_belt), ("shade", mirror_d(coat_belt)),
                 ("line", polyline([(158, 470), (184, 472)])), ("line", mirror_d(polyline([(158, 470), (184, 472)]))),
                 ("accent", ellipse(186, 380, 4, 4)), ("accent", ellipse(214, 380, 4, 4)),
                 ("accent", ellipse(186, 430, 4, 4)), ("accent", ellipse(214, 430, 4, 4))],
        "cardigan": [("fill", smooth_closed(cardigan)), ("fill", mirror_d(smooth_closed(cardigan))),
                     ("shade", rib), ("shade", mirror_d(rib)),
                     ("line", polyline([(188, 222), (192, 300), (193, 448)])),
                     ("line", mirror_d(polyline([(188, 222), (192, 300), (193, 448)])))],
    }
    return out


def shoes() -> dict[str, list[tuple[str, str]]]:
    heels = [(179, 922), (174, 944), (176, 959), (190, 966), (198.5, 958, "s"), (197.5, 932), (193, 924, "s")]
    flats = [(178, 934), (174, 948), (176, 960), (190, 966), (198.5, 959, "s"), (197.5, 938), (190, 932, "s")]
    boots = [(167, 760, "s"), (171, 800), (177, 880), (179, 920), (174, 944), (177, 959), (190, 966),
             (198.5, 958, "s"), (197.5, 936), (194, 900), (192, 840), (191, 760, "s")]
    sneakers = [(176, 922), (171, 944), (171, 962, "s"), (199.5, 964, "s"), (199.5, 940), (196, 922)]
    def pair(cls, d):
        return [(cls, d), (cls, mirror_d(d))]
    return {
        "heels": pair("fill", smooth_closed(heels)) + pair("line", curve((181, 932), (186, 940), (192, 940), (196, 934))),
        "flats": pair("fill", smooth_closed(flats)) + pair("shade", ellipse(188, 944, 5, 3)),
        "boots": pair("fill", smooth_closed(boots)) + pair("shade", poly([(167, 760), (191, 760), (191.5, 776), (168.5, 776)])),
        "sneakers": pair("fill", smooth_closed(sneakers)) + pair("sole", poly([(171, 952), (199.5, 953), (199.5, 964), (171, 962)]))
        + pair("line", polyline([(182, 928), (192, 930)])) + pair("line", polyline([(181, 936), (193, 938)])),
    }


def bags() -> dict[str, list[tuple[str, str]]]:
    return {
        "handbag": [("strap", curve((276, 516), (276, 474), (318, 474), (318, 516))),
                    ("fill", smooth_closed([(266, 514, "s"), (328, 514, "s"), (335, 586, "s"), (259, 586, "s")])),
                    ("shade", smooth_closed([(265, 514, "s"), (329, 514, "s"), (331, 540, "s"), (297, 554), (263, 540, "s")])),
                    ("metal", ellipse(297, 550, 4.5, 4.5))],
        "tote": [("strap", polyline([(274, 506), (288, 466), (306, 466), (320, 506)])),
                 ("fill", poly([(256, 505), (338, 505), (347, 612), (247, 612)])),
                 ("shade", poly([(256, 505), (338, 505), (339, 518), (255, 518)]))],
        "clutch": [("fill", smooth_closed([(266, 488, "s"), (334, 488, "s"), (334, 530, "s"), (266, 530, "s")])),
                   ("shade", poly([(266, 488), (334, 488), (300, 512)])),
                   ("metal", ellipse(300, 510, 3.5, 3.5))],
        "crossbody": [("strap", polyline([(170, 172), (262, 420)])),
                      ("fill", smooth_closed([(252, 418, "s"), (306, 418, "s"), (308, 470, "s"), (250, 470, "s")])),
                      ("shade", poly([(252, 418), (306, 418), (307, 440), (279, 448), (251, 440)])),
                      ("metal", ellipse(279, 444, 3.5, 3.5))],
    }


def small_items() -> dict[str, list[tuple[str, str]]]:
    bracelet = poly([(104, 442), (124, 446), (124, 455), (103, 451)])
    return {
        "necklace": [("strap", curve((184, 160), (186, 190), (214, 190), (216, 160))),
                     ("fill", smooth_closed([(200, 196), (206, 204), (200, 216), (194, 204)]))],
        "earrings": [("line", polyline([(169, 96), (169, 104)])), ("line", polyline([(231, 96), (231, 104)])),
                     ("fill", ellipse(169, 108, 4.5, 5.5)), ("fill", ellipse(231, 108, 4.5, 5.5))],
        "bracelet": [("fill", bracelet), ("fill", mirror_d(bracelet))],
        "watch": [("fill", mirror_d(bracelet)), ("metal", ellipse(286, 450, 7, 7)), ("accent", ellipse(286, 450, 4.5, 4.5))],
        "sunglasses": [("fill", ellipse(187, 84, 11, 7.5)), ("fill", ellipse(213, 84, 11, 7.5)),
                       ("line", polyline([(197, 82), (203, 82)])),
                       ("line", polyline([(176, 82), (170, 80)])), ("line", polyline([(224, 82), (230, 80)]))],
        "scarf": [("fill", smooth_closed([(176, 150), (200, 146), (224, 150), (226, 166), (200, 178), (174, 166)])),
                  ("fill", smooth_closed([(196, 166), (212, 166), (214, 250), (217, 330, "s"), (199, 334, "s"), (199, 250)])),
                  ("shade", smooth_closed([(184, 162), (200, 170), (216, 162), (214, 172), (200, 178), (186, 172)])),
                  ("line", polyline([(201, 334), (201, 344)])), ("line", polyline([(207, 334), (207, 345)])),
                  ("line", polyline([(213, 332), (213, 343)]))],
        "belt": [("fill", poly([(156, 319), (244, 319), (243.5, 334), (156.5, 334)])),
                 ("metal", poly([(192, 316), (208, 316), (208, 337), (192, 337)])),
                 ("fill", poly([(195, 320), (205, 320), (205, 333), (195, 333)]))],
        "sunhat": [("fill", ellipse(200, 58, 80, 15)),
                   ("fill", smooth_closed([(170, 60, "s"), (172, 32), (186, 18), (214, 18), (228, 32), (230, 60, "s")])),
                   ("shade", poly([(171, 44), (229, 44), (230, 56), (170, 56)]))],
        "beret": [("fill", smooth_closed([(162, 60), (168, 38), (196, 24), (234, 30), (246, 48), (234, 62), (198, 66)])),
                  ("shade", ellipse(200, 23, 4, 3))],
        "beanie": [("fill", smooth_closed([(167, 74, "s"), (167, 48), (181, 28), (200, 21), (219, 28), (233, 48), (233, 74, "s")])),
                   ("shade", poly([(167, 60), (233, 60), (233, 76), (167, 76)])),
                   ("line", polyline([(185, 30), (182, 58)])), ("line", polyline([(200, 22), (200, 58)])),
                   ("line", polyline([(215, 30), (218, 58)]))],
    }


VARIANT_SLOT = {
    "tee": "top", "blouse": "top", "sweater": "top", "tank": "top",
    "pants": "bottom", "shorts": "bottom", "skirt_mini": "bottom", "skirt_midi": "bottom", "skirt_maxi": "bottom",
    "dress_mini": "dress", "dress_midi": "dress", "dress_maxi": "dress",
    "blazer": "outerwear", "coat": "outerwear", "cardigan": "outerwear",
    "heels": "shoes", "flats": "shoes", "boots": "shoes", "sneakers": "shoes",
    "handbag": "bag", "tote": "bag", "clutch": "bag", "crossbody": "bag",
    "necklace": "jewelry", "earrings": "jewelry", "bracelet": "jewelry", "watch": "accessory",
    "sunglasses": "accessory", "scarf": "scarf", "belt": "belt",
    "sunhat": "hat", "beret": "hat", "beanie": "hat",
    "nails_almond": "nails", "nails_round": "nails", "nails_square": "nails", "nails_french": "nails",
}


def svg_doc(name: str, paths: list[tuple[str, str]], slot: str) -> str:
    body = "\n".join(f'  <path class="{cls}" d="{d}"/>' for cls, d in paths)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 1000" '
        f'data-name="{name}" data-slot="{slot}">\n{body}\n</svg>\n'
    )


def main() -> None:
    mann = ROOT / "assets" / "mannequins"
    tmpl = ROOT / "assets" / "clothing_templates"
    mann.mkdir(parents=True, exist_ok=True)
    tmpl.mkdir(parents=True, exist_ok=True)
    for old in ("hair_back.svg", "hair_front.svg"):
        (mann / old).unlink(missing_ok=True)
    for name, paths in body_layers().items():
        (mann / f"{name}.svg").write_text(svg_doc(name, paths, "body"), encoding="utf-8")
    for style, parts in hair_styles().items():
        for part, paths in parts.items():
            (mann / f"hair_{style}_{part}.svg").write_text(svg_doc(f"hair_{style}_{part}", paths, "hair"), encoding="utf-8")
    for name, paths in mannequin_nails().items():
        (mann / f"{name}.svg").write_text(svg_doc(name, paths, "nails"), encoding="utf-8")
    garments = {**tops(), **bottoms(), **dresses(), **outerwear(), **shoes(), **bags(), **small_items(),
                **nail_templates()}
    for name, paths in garments.items():
        (tmpl / f"{name}.svg").write_text(svg_doc(name, paths, VARIANT_SLOT[name]), encoding="utf-8")
    print(f"wrote body, {len(hair_styles())} hairstyles, {len(NAIL_SHAPES)} nail shapes, {len(garments)} garment templates")


if __name__ == "__main__":
    main()
