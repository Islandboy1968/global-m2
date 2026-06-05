# Design Brief — GMI Risk Monitor → Real Vision Restyle

**For:** Claude Design
**Task:** Restyle the working GMI Risk Monitor dashboard into the **Real Vision
dark-dashboard format** (the same aesthetic you delivered for the GMI Compounding
Machine) and clean up the visual design. **Behaviour, data, and calculations stay
exactly as they are — this is a re-skin, not a rebuild.**

---

## The working file
- **Live prototype:** https://islandboy1968.github.io/global-m2/dashboard-risk-monitor/index.html
- **Source:** `Islandboy1968/global-m2` → `dashboard-risk-monitor/index.html`
- It's a single self-contained `index.html` — vanilla JS + inline SVG charts, **zero
  external dependencies** (no frameworks, no CDNs, no fonts loaded). Keep it that way
  (or, if you add a webfont, load it the way the Compounding Machine does).

## ⚠ The one hard constraint — the data injection contract
A pipeline rewrites **only** the block between these markers on every refresh:
```
// __PIPELINE_DATA_START__   …   // __PIPELINE_DATA_END__
```
**Do not rename, reshape, or remove those variables or the markers.** Restyle
everything *outside* that block (the HTML, CSS, and the render JS that reads the
variables). The injected variables you can rely on:

| Variable | Shape | Drives |
| --- | --- | --- |
| `isProSubscriber` | bool | Pro paywall gate |
| `lastUpdatedStr` | string | header "Last Updated" |
| `m2Roc` | `{yoy, mom6}` | the two RoC chips |
| `m2ChartData` / `ismChartData` | `[{d,c,s,g}]` | the two trend mini-charts (`c`=value, `s`=signal band, `g`=1 rising/0 falling) |
| `proPositions` / `alphaAssets` | `[{asset,ticker,trend,trendChange,price,category,since,secular,vol30d,regime,annVol}]` | the two tables |
| `m2Trend`/`ismTrend` (`"green"`/`"red"`), `m2Since`/`ismSince`, `ismValue` | — | regime banner + indicator boxes |

`trend`/`secular` use `"green"`/`"red"` (rising/falling); `trendChange` drives the
pulsing "New Buy/Sell" badge; `regime` is `"Normal"`/`"Extreme"`.

---

## Screens / layout (preserve all of it, top → bottom)
1. **Header** — title "GMI Risk Monitor", subtitle, a tier tag (RV PRO / RV ALPHA /
   GUIDE that swaps with the active tab), "Last Updated" date. Three tabs:
   **RV Pro Positions · RV Alpha Trends · How To Use This**.
2. **Executive status bar** — one line: current regime + a pulsing "N signal changes:
   …" chip (or "No signal changes this week").
3. **Macro Regime banner** — a colored box whose label/colour is set by JS from
   `m2Trend × ismTrend` (Full Expansion / Early Cycle / Late Cycle / Contraction),
   with a description paragraph. Below it, **two indicator columns**:
   - **Liquidity Trend** (Global M2): Rising/Falling signal + "Signal Since" + two RoC
     chips (YoY, 6m/6m) + an SVG mini-chart.
   - **Business Cycle Trend** (ISM): Rising/Falling + "Signal Since" + an SVG mini-chart.
   - Plus the editorial footnote + the "*proxy for the GMI Global Liquidity Index" note.
4. **Pro tab** — heading + the positions **table**; a TradingView note; and the
   **Pro paywall overlay** (when `isProSubscriber` is false: first 2 rows preview,
   the rest blurred, with an "Unlock GMI Pro Signals" card + Subscribe button).
5. **Alpha tab** — heading + the benchmarks table (same schema).
6. **How To Use tab** — the long-form guide (several explainer cards).
7. **Footer** — methodology fine print + "Global Macro Investor © 2026".

**Table columns:** Asset · Ticker · Price · 30d Vol · Risk · Secular Trend · Weekly
Trend · Signal Change · Since. (Vol has a Normal/Risky/High colour band; Weekly &
Secular are green/red badges with ↑/↓ arrows; Signal Change is the pulsing badge.)

**SVG mini-charts (`renderTrendChart`):** a close line + a dashed SuperTrend band
(green when rising / red when falling, drawn as segments + dots) + a subtle area fill
+ first/mid/last date labels + a coloured "current" dot. Restyle the strokes/fills to
RV; keep the chart's data mapping intact. (They were recently made taller; keep them
generous in height.)

---

## Real Vision design direction (match the Compounding Machine restyle)
Use the **same tokens** you used for the GMI Compounding Machine, so the two
dashboards are visually consistent:
```
bg #0a0d14 (radial glow at 70% -10% → #131a26)   card #10141d   card-2 #0d1119   raise #161b26
hairline rgba(255,255,255,0.06)   hairline-strong rgba(255,255,255,0.10)
text #e9ecf3   muted #8b93a6   faint #5b6477
lime #c3f53c (brand accent)   green #34c759 (rising/+)   red #f04f5f (falling/−)
gold #f5c451 (alerts/cash)   cyan #22d3ee   purple #b794f4   blue #60a5fa
Font: Hanken Grotesk, tabular figures (font-variant-numeric: tabular-nums lining-nums)
Cards radius 16 · pills 99 · 1px hairlines only · NO drop shadows · quiet 180ms eases
```
**Token mapping from the current GMI styling:** GMI gold `#c9a96e` → RV **lime**;
Söhne/JetBrains Mono → **Hanken Grotesk** (tabular figures, no separate mono);
signal dots `#4ade80/#f87171` → RV **green/red**; the amber "New Buy/Sell" badge
`#fbbf24` → RV **gold** `#f5c451`; the navy gradient bg → the RV `#0a0d14` radial.

**Fidelity:** high — final colours, type, spacing, and chart styling, faithful to RV.

---

## Clean-up notes (designer's discretion)
- The header is heavy (40px padding, big tag row) — tighten to the RV header rhythm.
- Tables are dense; apply RV's hairline-row treatment and tabular figures for clean
  number alignment (drop the monospace).
- The regime banner + two indicator columns can read more like RV "summary tiles".
- Balance the two mini-charts and give them an RV chart treatment (transparent panel,
  hairline gridlines, restrained strokes) consistent with the CM charts.
- Keep the **green = rising / red = falling** semantics and the pulsing change badge —
  those carry meaning.

## Deliverable
A restyled `index.html` (self-contained) that renders identically in behaviour, reads
the same injected variables, preserves the markers, and looks like a Real Vision
dashboard consistent with the Compounding Machine. A short README of the tokens/
decisions (as you did for the CM) is welcome.
