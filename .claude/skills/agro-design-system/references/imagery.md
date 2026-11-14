# Imagery

## What we use

Real artwork, not drawings made by an AI agent. The team asked for real drawings and designs; generated SVG illustrations looked amateur.

The current set is in `assets/images/` with full credits in `assets/images/CREDITS.md`: concept paintings by **Don Davis and Rick Guidice for NASA Ames Research Center (1975–1977)** from the space settlement studies (NASA SP-413). Farms, rivers and towns inside rotating habitats: hopeful, ecological, technological, which is the solarpunk tradition in its original form. They are NASA works and in the public domain.

| File | Where it's used |
|---|---|
| `torus-interior-davis-1975.jpg` | Landing hero |
| `torus-valley-guidice-1975.jpg` | Step 1, Describe the incident |
| `torus-wheel-guidice-1975.jpg` | Step 2, Read the NASA record |
| `torus-terraces-guidice-1975.jpg` | Step 3, Weigh the explanations |
| `farm-modules-guidice-1977.jpg` | Step 4, Compare rotations |
| `bernal-sphere-guidice-1976.jpg` | Data sources band |

## Allowed sources

1. **NASA Image and Video Library** (images.nasa.gov) and other NASA works: public domain. Credit NASA and the artist; never imply NASA endorsement; never use the NASA logo or "meatball".
2. **Wikimedia Commons** files under CC0, public domain, CC BY or CC BY-SA: keep the author, licence and link in `CREDITS.md`; CC BY-SA images keep their licence.
3. **Team-made** drawings, photos and designs, credited.
4. Other openly licensed artwork with a licence that allows web use and modification, recorded in `CREDITS.md`.

Not allowed: images copied from Pinterest, Behance, Dribbble, ArtStation or Google Images (they are almost always copyrighted and Pinterest is not a source, only a re-poster); AI-generated images; any photo or satellite image that could be mistaken for an observation of a user's field.

## How images are shown

- Illustration only. A NASA painting is never presented as data. Real satellite imagery of a case (e.g. HLS, once approved) is data and follows the evidence rules: `OBSERVED` label, source label, resolution.
- No captions under images (taste-skill). One credit line in the footer: "Art: Don Davis and Rick Guidice for NASA Ames Research Center, 1975–1977. Public domain."
- `alt` text describes the scene in plain words (EN and ES); decorative step images use `alt=""`.
- Always `width` and `height` attributes, `loading="lazy"` below the fold, `fetchpriority="high"` on the hero.
- Frames: `--radius-m` (steps, bands) or `--radius-l` top corners (hero), `object-fit: cover`, `overflow: hidden`. Hover zoom 1.03 only when the image is part of a link or a step.
- Scans come with grey or black borders: trim them before committing (the landing set is already trimmed). Export JPEG quality ~80, max 1600px wide for heroes and 960px for spots.
- Keep the page light: a dark space painting only inside the dark green band or as a small spot image.

## Adding new images

1. Find the image in an allowed source and note its ID, author, licence and URL.
2. Add the file to `assets/images/` (later `frontend/public/images/`) with a descriptive name (`subject-artist-year.jpg`).
3. Add a row to `CREDITS.md`.
4. Run the `agro-ui-review` skill. It checks alt text, dimensions and credits.
