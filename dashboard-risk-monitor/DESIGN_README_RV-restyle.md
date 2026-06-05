# GMI Risk Monitor — Real Vision Restyle

A re-skin of the working `index.html` into the **Real Vision dark-dashboard** format, matched
to the **GMI Compounding Machine** so the two read as one product family. **Behaviour, data,
calculations, and the markup structure are unchanged — this was a pure visual pass.**

## The data contract is intact
The block between `// __PIPELINE_DATA_START__` and `// __PIPELINE_DATA_END__` was **not
touched** — verified byte-for-byte identical to the source. Every injected variable keeps its
name and shape: `isProSubscriber, lastUpdatedStr, m2Roc, m2ChartData, ismChartData,
proPositions, alphaAssets, m2Trend, ismTrend, m2Since, ismSince, ismValue`. The render JS that
reads them is unchanged in logic; only literal colour/font strings inside it were swapped.

All behaviour is preserved: 3 tabs + swapping tier tag, the macro-regime banner (still keyed off
`m2Trend × ismTrend`), the two indicator columns with Rising/Falling + Signal Since + RoC chips +
SVG mini-charts, the executive status bar with the pulsing change chip, both tables (same 9
columns), the Pro paywall (2-row preview + blur, gated by `isProSubscriber`), the How-To guide,
and the footer.

## Tokens (identical to the Compounding Machine)
```
bg            #0a0d14  + radial-gradient(1200px 600px at 70% -10%, #131a26, #0a0d14 55%)
card          #10141d        card-inset  #0d1119
hairline      rgba(255,255,255,0.06)     hairline-strong rgba(255,255,255,0.10)
text          #e9ecf3        muted  #aab3c4        fine-print  #e4e9f2
lime (accent) #c3f53c        green (rising/+) #34c759     red (falling/−) #f04f5f
gold (alerts) #f5c451        cyan (price line) #22d3ee    blue (early cycle) #60a5fa
orange (high-risk vol) #f0884f
Font: Hanken Grotesk 400–800, tabular lining figures (no monospace)
Radii: cards 14–16 · pills 99 · 1px hairlines only · NO drop shadows · 180ms quiet eases
```

## Mapping applied (old GMI → RV)
| Old | New | Where |
|---|---|---|
| GMI gold `#c9a96e` / `#b8944f` | lime `#c3f53c` | tags, tab underline, headings, table headers, footnote rule, lock icon, Subscribe button |
| light-gold `#e8d5a8` | text `#e9ecf3` | dates, "Signal Since", emphasis text |
| green `#4ade80` | `#34c759` | rising signals, dots, badges, chart band |
| red `#f87171` | `#f04f5f` | falling signals, dots, badges, chart band |
| amber `#fbbf24` | gold `#f5c451` | "New Buy/Sell" badge, Late-Cycle regime, Risky vol band, signal-change chip |
| orange `#fb923c` | `#f0884f` | High-Risk vol band (kept a distinct orange so it doesn't read as a falling-trend red) |
| Söhne / JetBrains Mono | Hanken Grotesk (tabular) | everything; `.mono` now just forces tabular figures |
| navy gradient body | `#0a0d14` radial glow | page background |
| `rgba(0,0,0,·)` darks | `#10141d` / `#0d1119` surfaces | header (now transparent), status bar, indicator tiles, guide cards |

## Clean-up done (designer's discretion)
- **Header** tightened from 40px padding to the RV rhythm (24px, transparent), H1 to 31px/800;
  tags are now lime pills; tab row sits on a hairline rail with a lime active underline (no filled tab).
- **Tables** use hairline rows (1px `rgba(255,255,255,0.06)`), lime uppercase headers, a faint
  white zebra, and tabular figures for clean number alignment. Mono dropped.
- **Regime + indicator columns** read as RV summary tiles: inset `#0d1119` panels, hairline
  borders, 16px joined corners, regime tint driven by the live trend colours. The two chart
  tiles carry a green/red **trend-coloured border at 0.5 alpha** (keyed off `m2Trend`/`ismTrend`).

## Readability tuning (post-review)
- Muted body/label text raised from `#8b93a6` → **`#aab3c4`** throughout.
- Fine print (regime footnote + footer methodology + paywall/status helpers) raised to **`#e4e9f2`**
  (near body brightness) so it stays legible on the dark ground.
- Chart **date labels** brightened to `#b4bccc` and bumped to **10px** (were 8px / 0.4 alpha).
- Chart vertical scaling given headroom (`padTop 0.20 / padBot 0.16`) so the close line no longer
  slams the panel edges; data mapping unchanged.
- **Mini-charts** got the RV chart treatment: transparent panel, faint dashed **horizontal**
  hairline gridlines, a **cyan** close line (1.75px) to match the CM price series, restrained
  green/red dashed SuperTrend segments + dots, cyan area fill, and a ringed current-price dot.
  Heights kept generous (185 / 215px).
- **No emoji** (brand rule): the ⚠️ in the change badge and status chip was removed; the pulsing
  gold badge + text carry the alert.

## Deliverable
- `Risk Monitor.html` — self-contained, no external deps except the Hanken Grotesk webfont
  (loaded the same way the Compounding Machine loads its font). Drop it onto the pipeline as
  `index.html`; the markers and variables line up unchanged.
