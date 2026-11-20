# Product specification — ColorMuse

**Tagline:** Your personal wardrobe. Your personal stylist.
**Audience:** exactly one person (the owner). No registration, no sharing, no public profiles.
**Platforms:** any modern browser on phone, tablet or desktop. Nothing to install.

## Modules

### Home
Personal greeting (display name from Settings), quick actions (Match a color, Add a piece,
Plan an outfit, Outfit studio), **Quick styling** (pick a color → complementary / analogous /
neutral swatches, link to the full matcher), recent outfits (mannequin previews), recently added
pieces, favorite combinations, and four occasion inspiration cards that open the planner preset.

### Color Matcher
Inputs (three tabs, choose which one to match with):
- **Manual** — category, primary color (named library or free picker), up to 3 secondary colors,
  pattern, shade (auto-detected light/medium/dark, correctable).
- **Photo** — upload, select the clothing region with crop sliders, optional background
  reduction, extracted dominant + secondary colors with shares, main color picker for correction.
- **Wardrobe** — any owned piece.

Context: occasion, style, and an optional shade filter for suggestions.
Output: seven harmony palettes; per category (shirts, skirts, pants, dresses, shoes, handbags,
jewelry, accessories, outerwear — minus categories that conflict with the input) four
suggestions with swatch, name, 0–100 score, harmony rule, explanation and a component
breakdown; matching pieces already owned; **nail polish suggestions**; **colors that flatter
the owner's hair color**. Actions: build a complete outfit in the Studio; save to history.

### My Wardrobe
Categories: tops, bottoms, dresses, outerwear, shoes, bags, jewelry, accessories, scarves,
belts, hats — each with typed subcategories (e.g. Midi skirt, Ankle boots) that drive the
garment silhouette. Fields: name, type, main + secondary colors, shade, pattern, brand, seasons,
styles, occasions, notes, favorite, photo. Operations: add, edit, delete (with confirmation and
photo removal), view details, search, filter (category, favorites, season), sort (newest, oldest,
name, category, color light→dark, favorites), pagination (24/page), "Match this piece".

### Outfit Studio
Single outfit model with two synchronized visualizations:
- **Flat-lay**: Editorial / Grid / Minimal layout templates; each piece shown as the owner's
  photo or a recolored garment template; PNG export.
- **Mannequin**: layered SVG croquis; tops, bottoms, dresses, outerwear, shoes, bags, jewelry,
  accessories, scarves, belts, hats; recoloring and 7 fabric patterns; **7 hairstyles, any hair
  color, skin tone, 4 nail shapes with any polish color**; PNG export.

Editing is form-based (choose / recolor / remove / add pieces). It is intentionally **not**
drag-and-drop. Live outfit score with breakdown and notes, hairstyle and nail suggestions,
save, save as new, new look.

### Occasion Planner
Occasions: casual, office, date night, party, wedding guest, travel, beach, formal, dinner,
interview, daily errands. Optional style and season. Generates 2–8 complete, diverse looks
**only from owned pieces**, each finished with a suggested nail polish and hairstyle; open in
studio or save.

### Saved Looks
Grid with mannequin preview, palette, score, notes; edit (opens Studio), duplicate, favorite,
delete, notes, assign to collections; collections create / rename / delete; search, filter by
collection, occasion, favorites; PNG export (flat-lay and mannequin).

### Settings
Style profile (name, favorite colors, avoided colors, preferred styles, occasions, seasons),
hair & beauty defaults (hairstyle, hair color, skin tone, nail shape), scoring weights,
account (change password, sign out), data (backup ZIP + JSON, restore, delete all personal data).

## Non-goals (initial release)
AI stylist (architecture leaves room — see ARCHITECTURE.md), multi-user, social sharing,
true garment segmentation, drag-and-drop editing.

## Definition of done → where it's satisfied
| # | Requirement | Where |
|---|---|---|
| 1–2 | Hosted site, secure login | Streamlit Cloud + Supabase Auth (DEPLOYMENT.md, SECURITY.md) |
| 3–5 | Add clothing, upload photos, extract/correct colors | My Wardrobe |
| 6 | Color recommendations | Color Matcher |
| 7 | Manage wardrobe | My Wardrobe |
| 8–10 | Create outfits, flat-lay, mannequin | Outfit Studio |
| 11 | Save & edit outfits | Studio, Saved Looks |
| 12 | Occasion planning | Occasion Planner |
| 13 | Organize favorites | Saved Looks (favorites, collections) |
| 14 | Export images | Studio, Saved Looks |
| 15 | Data survives restarts | Supabase persistence (tests: persistence suite) |
