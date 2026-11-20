# Color engine

Deterministic, explainable and AI-free. Code: `src/core/`.

## Color spaces (`color_convert.py`)
- Hex ⇄ RGB ⇄ HSL / HSV (stdlib `colorsys`), RGB ⇄ XYZ ⇄ **CIELAB (D65)**, Lab → LCh.
- **CIEDE2000** perceptual distance, verified against Sharma et al. (2005) reference pairs and
  scikit-image (`deltaE_ciede2000`) to 1e-6.
- WCAG relative luminance & contrast ratio, perceptual lightness `L*`, chroma `C*`,
  shade classification (light ≥ 70 L*, medium ≥ 40, dark).
- scikit-image is used for vectorised work on photos; scalar code is pure Python (fast for
  scoring ~100 candidates).

## Color library (`color_library.py`)
97 named fashion colors in families (whites, beiges, browns, grays, blues, reds, pinks,
oranges, yellows, greens, purples, metallics) with neutral flags; nearest-name lookup by
CIEDE2000; neutral detection (library neutral within ΔE<4, or chroma < 9); undertone
(warm/cool/neutral from Lab hue). Seeded into Supabase via `scripts/generate_color_seed.py`.

## Harmony (`harmony.py`)
Rules on the HSL wheel: **complementary** (180°), **analogous** (±30°), **triadic** (±120°),
**split complementary** (180°±30°), **monochromatic** (same hue, lightness steps),
**neutral** (undertone-matched neutrals with lightness contrast), **contrast** (opposite depth).
Targets are clamped to wearable saturation/lightness and snapped to distinct library colors.

`classify_relation(a, b)` finds the relationship two colors form and a quality 0–1 using
gaussian peaks at each ideal angle (tolerances 10–18°); gaps between harmonies floor at 0.38;
near-identical colors score lower than real tonal pairs; low-saturation colors are forgiving.
Any pairing with a neutral is "neutral" (0.86–0.90).

## Scoring (`scoring.py`)
Every component returns 0–1 plus a sentence. Default weights (editable in Settings,
normalised to 100%):

| Component | Weight | What it measures |
|---|---|---|
| Color harmony | 35% | relation quality; +0.08 when echoing a secondary color of a printed piece |
| Contrast & balance | 20% | L* difference (sweet spot ≈ 15–55), penalty when two intense colors compete |
| Category compatibility | 15% | how forgiving the category is with neutral / metallic / muted / bright colors (e.g. metals for jewelry, neutrals for shoes and coats); ×0.7 when two patterns clash |
| Occasion | 10% | per-occasion profile: ideal L*/C*, favoured families/colors, colors to avoid (e.g. white for wedding guests) |
| Style | 10% | per-style profile (classic, minimalist, romantic, chic, bohemian, edgy, sporty, glam, preppy) |
| Personal preference | 10% | closeness to favorite colors (+), avoided colors (−); neutral 0.7 when unset |

Total = Σ weight × component × 100.

## Recommendations (`recommender.py`)
For each target category, every library color (metals only where they make sense) is scored
against the base; results are sorted by score then name and diversified (distinct families,
≤2 per harmony rule, relaxed only when needed). Owned pieces are scored the same way
("Already in your wardrobe"), respecting subcategories (skirts vs pants).

## Outfits (`outfit_engine.py`)
`score_outfit` uses visual weights per slot (dress 1.6 … jewelry 0.3, nails 0.25):
weighted pairwise harmony, ≤3 accent hues, contrast between main pieces and shoes vs
bottom/dress, category fit, one-statement-pattern rule, completeness, occasion fit including a
**garment-type × occasion suitability table** (clutch → evening, tote → work, sneakers ✗ interview…),
the owner's own occasion/style tags, favourites — plus notes (palette rule, tonal/contrast,
hair-color harmony, nails).

`generate_outfits` (Occasion Planner) is a deterministic beam search over owned pieces:
season filter → top-8 per slot by single-item fit → all top×bottom and dress bases → best shoes →
optional outerwear/bag/jewelry/belt/scarf/accessory/hat kept only when they improve the
objective (displayed score + practical suitability), with layering rules by season/occasion →
diversity (no repeated main piece when avoidable) → nail polish + hairstyle finishing.

## Beauty (`beauty.py`)
- **Nails**: every polish shade scored against each garment (weighted by visibility), bonus for
  echoing shoes/bag and for skin-tone nudes; diversified by family.
- **Hairstyles**: rules for occasion, neckline (scarf/sweater → up-dos; V-neck/dress → waves),
  hats (no top bun), earrings/necklace (show them off), coat collars; short-hair owners only get
  short styles.
- **Hair color**: colors that flatter the owner's hair near the face; warning when a top is
  almost the same color as the hair.

All behaviour is covered by `tests/test_color_engine.py` and `tests/test_outfits_and_beauty.py`.
