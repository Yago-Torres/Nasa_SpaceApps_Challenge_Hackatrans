# The Field Survey world

## Why a "world" at all

impeccable's main lesson: generated UIs converge because every axis gets the category default (an Inter-on-grey dashboard, a dark "cockpit" for anything technical, cards everywhere). The way out is to commit to a visual world taken from the audience's own culture and let it decide type, palette, density and one signature move, while layout, navigation and controls stay standard so the tool stays easy to use.

The first proposal for this project failed exactly there: it dressed working screens as an instrument panel (dark readouts, data plates, a pulsing recording dot). impeccable calls that a costume: a world taken from a tool the audience operates comes back as fancy dress on a screen that should simply work.

## Where this world comes from

The users are farmers, agronomists and community reviewers (pilot: Ebro valley, Spain), plus hackathon judges. Their graphic culture includes:

| Source | What we take | What we don't take |
|---|---|---|
| **Topographic and soil survey maps** (e.g. IGN sheets) | A **legend**: a small symbol per kind of thing, explained once and used everywhere. Dashed lines for uncertain boundaries, triangles for verified reference points. Italic serif for natural names. | Contour patterns as decoration, fake map textures, invented geodata. |
| **Technical-drawing title blocks** (ISO 7200 cartouche) | The **case title block**: one ruled block stating what this is, ID, scale, date, status, reviewer. | Engineering-drawing borders, fold marks, blueprint blue. |
| **Herbarium sheets** | The **source label** (who, where, when, how, for every specimen) and **determination slips**: later reviewers add signed, dated notes without erasing earlier ones. That is our collaborative review. | Cream paper, pressed-plant imagery, typewriter fonts. |
| **Agricultural extension leaflets** | Plain language addressed to the farmer: what happened, what to check next. | Retro print styling. |

## How "industrial" shows up

- Honest structure: ruled title block, table rules, clear labels, aligned grid.
- Operability: standard controls, 44px targets, one primary action, predictable rail navigation.
- Precision: tabular numbers, units everywhere, resolution and checksum visible.

## How "solarpunk / hopecore" shows up

- The team palette: bright sky blue, living greens, pearl aqua grounds, yellow-green action. Light mode only.
- People's knowledge has the same standing as satellites: farmer reports and review slips get their own symbol, their own voice (serif italic) and a place beside the NASA data, not a footnote.
- Hope through repair: every error says how to fix it; every hypothesis says what measurement would settle it; rotation options look forward.
- What it's not: leaf clip-art, neon green on black, glass panels, sunbursts, decorative plant photos, AI-generated "field" imagery that could be mistaken for observations.

## Allowed ornament budget

- Workspace screens (Operate): zero ornament. The world is only palette, type, legend and the title block.
- Landing page (Persuade): the celestial hero band and the legend section. Optional: team-made line illustrations (1.5px stroke, one accent colour), credited, never photoreal fake fields.
- Report (Read): the title block at the top, the legend at the end, print-friendly.

## Ban list (with sources)

From impeccable (craft floor and detector): eyebrow labels above headings; numbered sections that aren't sequences; hero-metric templates; identical icon+heading+text cards; nested cards; gradient text; decorative glass/blur; coloured side borders over 1px; hard offset shadows; monospace as costume; system/overused display faces (Inter, Roboto, Fraunces, Geist, Plus Jakarta Sans, Space Grotesk); Unicode/emoji as icons; pulsing status dots; repeating-gradient stripes; bounce/elastic easing; cramped padding; light or dark chosen by category rather than by the scene of use (we chose light because people use it outdoors and the team asked for it).

From taste-skill (copy tells): slop words (seamless, empower, unlock, robust, revolutionary, cutting-edge…), stock lines ("In today's…", "Say goodbye to…"), stat strips, "X. Y." two-fragment headings, contrast frames ("not X but Y") repeated, invented specifics presented as real, virtue words about ourselves (honest, genuinely…), em-dash-heavy prose, arrows glued to links.

Mechanical check: `npx -y impeccable@4.8.0 detect --json <files>` (run by the `agro-ui-review` skill).
