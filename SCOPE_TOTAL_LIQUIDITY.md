# SCOPE — GMI Total Global Liquidity (the real headline measure)

> Status: **SCOPING / not built.** Captures the target measure, the data we have
> vs need, a phased build, a validation plan, and the formula decisions only Raoul
> can lock. The current dashboard headline is **Global M2** (summed M2 in USD) —
> a good first-order proxy, but NOT the GMI flagship. Written 2026-06-09.

## 1. What we're building (and the key insight)

GMI Total Global Liquidity is **not** money supply (Global M2) and **not** a sum of
central-bank balance sheets. It is a **layered Net Liquidity** measure, summed
across the major economies in USD. Per region:

```
Region Net Liquidity ≈  Central-bank balance sheet     (e.g. Fed WALCL)
                        − government cash balance        (e.g. US TGA)
                        − liquidity-draining facilities  (e.g. US RRP)
                        + private money creation         (bank credit / broad money)
```

- The **balance sheet is the first term**, but it must be **netted** (− TGA − RRP)
  and **combined with the private layer**. Raw-summed balance sheets mislead today
  because (a) QT shrinks them, (b) no netting, (c) they omit the bank-credit /
  Treasury-issuance channel that is currently doing most of the work. (See the
  −0.2% YoY probe result vs GMI's published +8%.)
- GMI's published recipe, from the monthlies:
  - **Fed Net Liquidity** = WALCL − TGA − RRP
  - **US Total Liquidity** = Fed Net Liquidity + M2 + bank security holdings
    *(GMI Nov 2025: "FNL + M2 + Bank Security Holdings… adds another $5tn")*
  - **Total Global Liquidity** = US Total Liquidity + rest-of-world + China, in USD
    *(GMI Apr 2026: "what lies beneath… US Total Liquidity… time to add in China")*

## 2. Data inventory — have vs need

| Region | CB balance sheet | Gov cash (TGA-eq) | Drain (RRP-eq) | Bank credit | Broad money M2 |
|--------|:---:|:---:|:---:|:---:|:---:|
| **US** | WALCL ✅ | WTREGEN ✅ | RRPONTSYD ✅ | TOTBKCR ✅ | USM2 ✅ |
| EZ | EUCBBS ✅ | ⚠️ ECB gov deposits | n/a | ⚠️ ECB MFI loans | EUM2 ✅ |
| JP | JPCBBS ✅ | ⚠️ | n/a | ⚠️ | JPM2 ✅ |
| UK | GBCBBS ✅ | ⚠️ | n/a | ⚠️ | GBM2 ✅ |
| CN | CNCBBS ✅ | ⚠️ | n/a | ⚠️ TSF | CNM2 ✅ |

- **US**: full Net Liquidity is already built — `us_liquidity.py` computes
  `WALCL − TGA − RRP + bank credit`. This leg is done and verified.
- **Non-US**: CB balance sheets (`…CBBS`) and broad money (`…M2`) pull cleanly
  (probed live, all OK). The US-style netting inputs (government cash, draining
  facilities, bank securities) are patchy abroad — the binding constraint.

## 3. The double-counting trap (the methodological crux)

You **cannot** simply add "CB balance sheet + M2": central-bank reserves are base
money that already backs part of broad money, so summing them double-counts. GMI
avoids this by **netting** (− TGA − RRP) and by using **bank credit** as the private
term rather than raw balance sheet. Any build must pick ONE coherent private-liquidity
measure per region (broad money OR bank credit), not stack overlapping ones.

## 4. Phased build

- **v0 (today):** Global M2 headline. Best simple proxy; matches GMI's growth/ATH
  narrative reasonably (+6.3% vs ~8%) and correlates 0.95/0.99 with BTC/NDX.
- **v1 — Global Total Liquidity (tractable, GMI-aligned):**
  `US Total Liquidity (full netting, have it) + Σ non-US broad money (M2, USD) + China explicit`.
  Strictly richer than Global M2 on the US leg (adds netted Fed liquidity + US bank
  credit); a defensible global aggregate from data we already pull. Keep **Global M2
  as its own separate chart** alongside it.
- **v2 — regional Net Liquidity:** replace each major region's M2 leg with a netted
  Net Liquidity leg (CB balance sheet − gov cash + regional bank credit) as those
  inputs are sourced (ECB SDW, BoJ, BoE, PBoC/TSF). Moves it from proxy toward the
  true GMI construction.

## 5. Validation plan (how we decide each version is real)

A version ships only if it passes, measured against the data:
1. **Growth/level sanity:** YoY ≈ GMI's published ~8%/yr, near an all-time high
   (the CB-balance-sheet-only attempt FAILED this: −0.2%, falling — correctly rejected).
2. **Risk-asset test (GMI's own logic):** lead/correlation to BTC & NDX must be
   **≥ Global M2's** (0.95 / 0.99). It has to be *additive*, not just different.
3. **US-leg cross-check:** the US contribution must reconcile with the existing
   US Liquidity tab to the dollar.
4. **Source-verified freshness:** every new leg registered in `verify_data.py`.

## 6. Decisions only Raoul can lock (blocking v1)

1. **Formula version:** FNL + M2, or FNL + M2 + bank securities (the "+$5tn" update)?
2. **Private leg abroad:** broad money (M2) or bank credit for non-US regions in v1?
3. **Coverage:** which economies in the aggregate — G5, G10, or all 47?
4. **Netting abroad:** for v2, which government-cash / draining series per region,
   and how to handle regions where they don't exist.
5. **Headline swap:** does Total Global Liquidity *replace* Global M2 as the headline
   (Global M2 demoted to a sub-chart), or sit alongside it?

## 7. Build effort

- v1: ~1 focused session. All inputs already pull; the US leg exists; the work is
  the composition, USD alignment, double-counting discipline, a new chart, and
  `verify_data` registration. Reversible, additive, behind a new chart (doesn't
  disturb the live headline until approved).
- v2: incremental, one region at a time, gated on sourcing each region's netting
  inputs.
