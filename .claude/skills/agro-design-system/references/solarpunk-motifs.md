# Solarpunk motifs — what's allowed, what it means, where it goes

Solarpunk is the modern, hopeful layer that keeps the industrial base from feeling cold. Every motif below **encodes something** about the product's values (transparency, community knowledge, repair, growth). If you can't say what a decorative element means, cut it.

## Allowed motifs

### 1. Sun arc (signature)
- **Means**: progress of a case through the day — from the incident (dawn) through investigation (noon) to a better plan (dusk). Bringing evidence into the light.
- **Where**: journey band in the shell; static version on the landing page; tiny version in the cases table "Step" column.
- **How**: thin dashed arc in `--line`, stations as circles, sun as a solid `--sun` disc. See components.md.
- **Not**: a decorative sunburst behind headings; rays; glow effects.

### 2. Daylight palette
- **Means**: field use outdoors; openness.
- **Where**: the default theme. Solar gold and chlorophyll appear as **accents with roles** (sun, growth, farmer data), never as large gradient washes.

### 3. Leaf shape (`--radius-leaf`)
- **Means**: something a living person/field contributed.
- **Where**: FARMER_REPORTED tags, local note chips, timeline markers for farmer events, evidence-graph farmer nodes.

### 4. Organic radius and the human serif
- **Means**: human voice and community.
- **Where**: ReviewNote, invitations, collaboration panels, the landing hero statement, quotes from reviewed literature. Fraunces with `SOFT 100`.

### 5. Mycelium connectors
- **Means**: knowledge networks — evidence linking hypotheses and studies, communities linking cases.
- **Where**: evidence graph edges, "conflicting findings" connector in the Science desk, collaboration diagrams on the landing page.
- **How**: cubic Bézier SVG paths, 1.5px, `--growth` for supporting, `--line-strong` dashed for contradicting, round linecaps. Straight orthogonal lines remain for machine pipelines (data plate → chart). The contrast between the two line types is the point.

### 6. Growth line pattern (rare)
- **Means**: regeneration after the incident.
- **Where**: only (a) the landing hero background behind the instrument, (b) the empty state of a brand-new case, (c) the report cover. Nowhere in the cockpit.
- **How**: inline SVG pattern of thin branching lines (leaf venation) at 6–8% opacity of `--growth`, masked to fade toward content. Must not reduce text contrast; hidden in print and in high-contrast mode (`@media (forced-colors: active)`).

### 7. Line illustrations (optional)
- **Means**: coexistence of technology and agriculture (solar panels among crops, satellites over fields, hands with soil samples).
- **Where**: landing sections, empty states, 404.
- **How**: single-weight 1.5px strokes in `--ink`, one accent fill (`--sun` or `--growth`), no gradients. Drawn by the team or from properly licensed sources with attribution. Never AI-generated imagery that could pass as a real field photo or satellite image — that would contradict the product's honesty about observations.

## Not allowed (reads as kitsch or contradicts the product)

- Leaf/vine clip-art scattered as decoration; plant emoji in UI copy.
- Neon green on black, "eco" gradients, glassmorphism/greenhouse blur panels.
- Satellite imagery or photos used decoratively in a way that could be mistaken for the case's observations.
- Hand-drawn wobble on data marks (charts stay precise; organic shapes are for people, not measurements).
- Hazard stripes as general decoration (the striped tape is reserved for ILLUSTRATIVE data, so its meaning stays strong).

## Balance check

Per screen, count solarpunk elements beyond the shell's sun-arc. Cockpit and settings: 0–1. Intake, science desk, rotation lab: 1–2. Review and landing: up to 3. If a screen exceeds that, remove one.
