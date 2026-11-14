# Motion and interaction standard

Motion answers what a person did, and shows what changed. Nothing loops for decoration, nothing animates on scroll, and nothing waits at `opacity: 0` for an observer. All durations come from tokens, so `prefers-reduced-motion: reduce` turns everything off in one place (`assets/tokens.css` sets every `--dur-*` to 0 and `--lift` to 0).

Live reference: `assets/system.html` (hover, press and focus every control) and `assets/landing.html` (tabs, disclosure, toasts, chart, menu).

## Tokens

| Token | Value | Use |
|---|---|---|
| `--ease-out` | `cubic-bezier(.22,1,.36,1)` | every UI transition (exponential ease-out) |
| `--ease-in-out` | `cubic-bezier(.65,0,.35,1)` | rare: a slow ambient move the user can pause |
| `--dur-press` | 80ms | button press |
| `--dur-1` | 120ms | hover colour, border, background |
| `--dur-2` | 200ms | lift, arrow nudge, tab indicator, toast, menu fade |
| `--dur-3` | 320ms | disclosure height, drawer, image zoom |
| `--dur-4` | 600ms | chart bars growing when data arrives |
| `--lift` | −1px | hover lift for buttons (linked blocks use −2px) |
| `--shadow-hover` | soft offset shadow | hover depth; never a zero-blur block shadow |

## Patterns

| Interaction | Behaviour | CSS sketch |
|---|---|---|
| Button hover | background steps lighter, lift `--lift`, `--shadow-hover`, trailing arrow +3px | `transition: background-color var(--dur-1), transform var(--dur-2), box-shadow var(--dur-2)` |
| Button press | `translateY(0) scale(.98)`, shadow off, `--dur-press` | `.btn:active { … transition-duration: var(--dur-press) }` |
| Busy button | spinner before the label, label ends in "…", disabled only while the request runs, width kept | `aria-busy="true"` |
| Text link | underline thickens 1px → 2px; nav links draw an underline left to right | `background-size 0 → 100%` over `--dur-2` |
| Linked block (card that is a link) | lift −2px + shadow; its image scales 1.03 inside an `overflow: hidden` frame | `--dur-2` / `--dur-3` |
| Table row | background tint on hover | `--dur-1` |
| Input | border darkens on hover; focus ring appears instantly (no transition on focus) | — |
| Tabs | ARIA tabs; arrow keys, Home/End; a 3px indicator slides under the selected tab | `transform` + `width` over `--dur-2` |
| Disclosure | chevron rotates 180°, body opens with `grid-template-rows: 0fr → 1fr` | `--dur-3` |
| Mobile menu | fades and drops 6px; Esc closes and returns focus to the button | `--dur-2` |
| Drawer / bottom sheet | slides in from the edge; focus moves in, returns on close; `overscroll-behavior: contain` | `--dur-3` |
| Toast | rises 8px and fades in; closes after 6s, pauses on hover; has a close button; lives in an `aria-live="polite"` region | `--dur-2` |
| Chart data arriving | bars grow from the zero line with a 30ms stagger, only after a user action or the first time the chart enters the viewport | `--dur-4` |
| Tooltip | fades in on hover **and** keyboard focus; contains the same text as the accessible label | `--dur-1` |
| Sticky header | gains a hairline and faint shadow once the page scrolls | `--dur-2` |

## Rules

- Animate `transform`, `opacity`, colours and `grid-template-rows`; never `transition: all`; list properties.
- Every animation is interruptible: hovering out or pressing again reverses it.
- Never animate the scientific value itself (no count-ups of numbers, no morphing between datasets).
- No pulsing "live" dots, bounce or elastic easing, parallax, scroll-triggered fade-ins, or autoplaying carousels.
- Any motion longer than 5 seconds needs a pause control (WCAG 2.2.2). The current design has none.
- Test with `prefers-reduced-motion: reduce`: the page must be complete and usable with every duration at 0.
