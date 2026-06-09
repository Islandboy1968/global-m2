#!/usr/bin/env python3
"""
indicators_meta.py — the self-describing layer for the TEC dashboard.

WHY THIS EXISTS
===============
TEC's data/data.json is a stack of raw series (the global liquidity line plus
~45 macro leaves under us/big/cycle/exp/infl/labor/rates/housing/credit/china).
The numbers are there, but nothing in the payload tells a machine WHAT each
series is — its units, whether it leads or lags the cycle, or which direction is
"good". An AGENT reading the dashboard has to guess. This registry removes the
guess: it maps every leaf series (by its dotted path in data.json, e.g.
"cycle.fci" or "infl.core_yoy") to a small `meta` block.

It is the TEC counterpart to EA's indicators.py and emits the SAME meta field
set, so one parser ingests both dashboards (see DATA_CONTRACT.md §4).

`summarize.py` reads this to attach meta to each indicator in summary.json. The
human-readable titles are kept in lockstep with verify_data.EXPECTED (same
labels the health report prints) so the two never drift.

meta fields (matching EA's set)
-------------------------------
    title        Human-readable chart title.
    group        Dashboard tab the series lives on (layout + topical grouping).
    role         Topical role: liquidity | cycle | inflation | labor | rates |
                 housing | credit | china | structural | asset.
    timing       leading | coincident | lagging — its phase vs the business
                 cycle (drives how an AI weights it as a signal).
    unit         Display unit (verbatim, for axis/label).
    progress     "higher" | "lower" — which direction is the favourable read,
                 so a falling unemployment rate or mortgage rate is not misread
                 as deterioration. For non-directional cyclical series this is a
                 best-effort hint, not a value judgement.
    source       Upstream feed identifier(s).
    description  One-line plain-English summary.
"""

# Dotted data.json path -> meta. Keys match summarize.py's leaf walk and
# verify_data.py's json paths exactly.
META = {
    # ---- Headline -------------------------------------------------------
    "series": {
        "title": "GMI Total Global Liquidity", "group": "Global Liquidity",
        "role": "liquidity", "timing": "leading", "unit": "$ trillions",
        "progress": "higher", "source": "TradingView ECONOMICS (M2) + FX",
        "description": "Broad money across 47 economies valued in USD at spot FX "
                       "and summed — the Everything Code headline liquidity index."},
    "btc": {
        "title": "Bitcoin price", "group": "Global Liquidity", "role": "asset",
        "timing": "lagging", "unit": "$", "progress": "higher",
        "source": "TradingView INDEX:BTCUSD",
        "description": "Risk-asset overlay; lags global liquidity by ~10 weeks."},
    "ndx": {
        "title": "Nasdaq 100 price", "group": "Global Liquidity", "role": "asset",
        "timing": "lagging", "unit": "$", "progress": "higher",
        "source": "TradingView NASDAQ:NDX",
        "description": "Risk-asset overlay layered against the liquidity line."},

    # ---- US net liquidity ----------------------------------------------
    "us.series": {
        "title": "US net liquidity (weekly)", "group": "US Liquidity",
        "role": "liquidity", "timing": "leading", "unit": "$ trillions",
        "progress": "higher", "source": "FRED (WALCL/TGA/RRP/TOTBKCR/SBCACBW)",
        "description": "GMI US Total Liquidity: WALCL - TGA - RRP + bank credit "
                       "(broad) / + securities held by banks (narrow)."},

    # ---- The Big Picture (structural, FRED) ----------------------------
    "big.lfpr":     {"title": "Labour force participation", "group": "Big Picture",
                     "role": "structural", "timing": "lagging", "unit": "%",
                     "progress": "higher", "source": "FRED:CIVPART",
                     "description": "Share of the population in the labour force."},
    "big.births":   {"title": "Birth rate", "group": "Big Picture",
                     "role": "structural", "timing": "lagging", "unit": "births",
                     "progress": "higher", "source": "FRED",
                     "description": "Structural demographic input to the long cycle."},
    "big.debt":     {"title": "Federal debt % GDP", "group": "Big Picture",
                     "role": "structural", "timing": "lagging", "unit": "% of GDP",
                     "progress": "lower", "source": "FRED:GFDEGDQ188S",
                     "description": "Federal debt held by the public as a share of GDP."},
    "big.interest": {"title": "Interest payments", "group": "Big Picture",
                     "role": "structural", "timing": "lagging", "unit": "$ billions",
                     "progress": "lower", "source": "FRED",
                     "description": "Federal interest expense — the fiscal-dominance pressure."},
    "big.y5":       {"title": "5y Treasury yield", "group": "Big Picture",
                     "role": "rates", "timing": "coincident", "unit": "%",
                     "progress": "higher", "source": "FRED:DGS5",
                     "description": "5-year Treasury constant-maturity yield."},

    # ---- Business Cycle -------------------------------------------------
    "cycle.ism":          {"title": "ISM PMI", "group": "Business Cycle",
                           "role": "cycle", "timing": "leading", "unit": "index (50=neutral)",
                           "progress": "higher", "source": "TradingView ECONOMICS:USBCOI",
                           "description": "Manufacturing PMI — expansion above 50."},
    "cycle.neworders":    {"title": "ISM new orders", "group": "Business Cycle",
                           "role": "cycle", "timing": "leading", "unit": "index (50=neutral)",
                           "progress": "higher", "source": "TradingView ECONOMICS",
                           "description": "Forward-looking demand component of the PMI."},
    "cycle.gdp":          {"title": "GDP QoQ", "group": "Business Cycle",
                           "role": "cycle", "timing": "coincident", "unit": "% QoQ SAAR",
                           "progress": "higher", "source": "TradingView ECONOMICS",
                           "description": "Quarterly real GDP growth, annualised."},
    "cycle.capex":        {"title": "Capex % GDP", "group": "Business Cycle",
                           "role": "cycle", "timing": "coincident", "unit": "% of GDP",
                           "progress": "higher", "source": "FRED:PNFI / FRED:GDP",
                           "description": "Nonresidential fixed investment as a share of GDP."},
    "cycle.capex_g":      {"title": "Capex growth", "group": "Business Cycle",
                           "role": "cycle", "timing": "coincident", "unit": "% YoY",
                           "progress": "higher", "source": "FRED:PNFI",
                           "description": "Nominal capex growth, year-on-year."},
    "cycle.services_ism": {"title": "ISM services PMI", "group": "Business Cycle",
                           "role": "cycle", "timing": "coincident", "unit": "index (50=neutral)",
                           "progress": "higher", "source": "TradingView ECONOMICS",
                           "description": "Services-sector PMI."},
    "cycle.m2_yoy":       {"title": "US M2 YoY", "group": "Business Cycle",
                           "role": "liquidity", "timing": "leading", "unit": "% YoY",
                           "progress": "higher", "source": "TradingView ECONOMICS:USM2",
                           "description": "US broad-money growth, year-on-year."},
    "cycle.services_neworders": {"title": "ISM services new orders", "group": "Business Cycle",
                           "role": "cycle", "timing": "leading", "unit": "index (50=neutral)",
                           "progress": "higher", "source": "TradingView ECONOMICS",
                           "description": "Forward demand in services."},
    "cycle.bc_composite": {"title": "Business-cycle composite", "group": "Business Cycle",
                           "role": "cycle", "timing": "coincident", "unit": "z-score",
                           "progress": "higher", "source": "derived",
                           "description": "Blended cycle gauge across the PMI/orders set."},
    "cycle.cyclical_impulse": {"title": "Cyclical impulse", "group": "Business Cycle",
                           "role": "cycle", "timing": "leading", "unit": "z-score",
                           "progress": "higher", "source": "derived",
                           "description": "Rate-of-change impulse in the cycle composite."},
    "cycle.fci":          {"title": "GMI FCI", "group": "Business Cycle",
                           "role": "cycle", "timing": "leading", "unit": "index",
                           "progress": "higher", "source": "derived from ISM",
                           "description": "Financial Conditions Index reconstruction; leads ISM ~9 months."},
    "cycle.fci_exoil":    {"title": "FCI ex-oil", "group": "Business Cycle",
                           "role": "cycle", "timing": "leading", "unit": "index",
                           "progress": "higher", "source": "derived from ISM",
                           "description": "FCI variant excluding the oil contribution."},

    # ---- Global Leading Edge (exports) ---------------------------------
    "exp.twexp_yy": {"title": "Taiwan exports YoY (semis proxy)", "group": "Global Leading Edge",
                     "role": "cycle", "timing": "leading", "unit": "% YoY", "progress": "higher",
                     "source": "TradingView ECONOMICS",
                     "description": "Taiwan export growth — a semiconductor-cycle bellwether."},
    "exp.krexp_yy": {"title": "South Korea exports YoY", "group": "Global Leading Edge",
                     "role": "cycle", "timing": "leading", "unit": "% YoY", "progress": "higher",
                     "source": "TradingView ECONOMICS",
                     "description": "Korean export growth — early global-trade signal."},
    "exp.jpmto_yy": {"title": "Japan machine tool orders YoY", "group": "Global Leading Edge",
                     "role": "cycle", "timing": "leading", "unit": "% YoY", "progress": "higher",
                     "source": "TradingView ECONOMICS",
                     "description": "Capex-cycle leading indicator from Japanese machine tools."},

    # ---- Inflation ------------------------------------------------------
    "infl.headline_yoy":  {"title": "Headline CPI YoY", "group": "Inflation",
                           "role": "inflation", "timing": "lagging", "unit": "% YoY",
                           "progress": "lower", "source": "FRED:CPIAUCSL",
                           "description": "Headline consumer price inflation."},
    "infl.core_yoy":      {"title": "Core CPI YoY", "group": "Inflation",
                           "role": "inflation", "timing": "lagging", "unit": "% YoY",
                           "progress": "lower", "source": "FRED:CPILFESL",
                           "description": "CPI excluding food and energy."},
    "infl.goods_yoy":     {"title": "Core goods CPI YoY", "group": "Inflation",
                           "role": "inflation", "timing": "lagging", "unit": "% YoY",
                           "progress": "lower", "source": "FRED",
                           "description": "Core goods inflation."},
    "infl.services_yoy":  {"title": "Core services CPI YoY", "group": "Inflation",
                           "role": "inflation", "timing": "lagging", "unit": "% YoY",
                           "progress": "lower", "source": "FRED",
                           "description": "Core services inflation (the sticky component)."},
    "infl.exshelter_yoy": {"title": "CPI ex-shelter YoY", "group": "Inflation",
                           "role": "inflation", "timing": "lagging", "unit": "% YoY",
                           "progress": "lower", "source": "FRED",
                           "description": "CPI excluding shelter."},
    "infl.be10":          {"title": "10y breakeven", "group": "Inflation",
                           "role": "inflation", "timing": "leading", "unit": "%",
                           "progress": "lower", "source": "FRED:T10YIE",
                           "description": "Market-implied 10-year inflation expectations."},
    "infl.umich":         {"title": "UMich 1y expectations", "group": "Inflation",
                           "role": "inflation", "timing": "leading", "unit": "%",
                           "progress": "lower", "source": "FRED",
                           "description": "University of Michigan 1-year inflation expectations."},
    "infl.accel":         {"title": "CPI 2nd derivative", "group": "Inflation",
                           "role": "inflation", "timing": "leading", "unit": "pp",
                           "progress": "lower", "source": "derived from FRED:CPIAUCSL",
                           "description": "Acceleration/deceleration of inflation (rate of change of YoY)."},

    # ---- Labor ----------------------------------------------------------
    "labor.unrate":   {"title": "Unemployment rate", "group": "Labor",
                       "role": "labor", "timing": "lagging", "unit": "%",
                       "progress": "lower", "source": "FRED:UNRATE",
                       "description": "Headline unemployment rate."},
    "labor.ot_yoy":   {"title": "Overtime hours YoY", "group": "Labor",
                       "role": "labor", "timing": "leading", "unit": "% YoY",
                       "progress": "higher", "source": "FRED",
                       "description": "Manufacturing overtime hours — an early labour-demand signal."},
    "labor.temp_yoy": {"title": "Temp help YoY", "group": "Labor",
                       "role": "labor", "timing": "leading", "unit": "% YoY",
                       "progress": "higher", "source": "FRED:TEMPHELPS",
                       "description": "Temporary-help payrolls — leads the broader labour cycle."},
    "labor.jolts":    {"title": "JOLTS hires", "group": "Labor",
                       "role": "labor", "timing": "coincident", "unit": "thousands",
                       "progress": "higher", "source": "FRED",
                       "description": "Hires from the JOLTS report."},
    "labor.claims":   {"title": "Initial jobless claims", "group": "Labor",
                       "role": "labor", "timing": "leading", "unit": "thousands",
                       "progress": "lower", "source": "FRED:ICSA",
                       "description": "Weekly initial unemployment claims — a fast labour signal."},

    # ---- Rates & Dollar -------------------------------------------------
    "rates.y10_yoy_z": {"title": "10y yield YoY (z-score)", "group": "Rates & Dollar",
                        "role": "rates", "timing": "coincident", "unit": "z-score",
                        "progress": "lower", "source": "FRED:DGS10",
                        "description": "Year-on-year change in the 10y yield, standardised."},
    "rates.oil_yoy":   {"title": "Oil YoY", "group": "Rates & Dollar",
                        "role": "rates", "timing": "leading", "unit": "% YoY",
                        "progress": "lower", "source": "TradingView",
                        "description": "Crude oil year-on-year — an inflation/cost impulse."},
    "rates.dxy":       {"title": "US dollar (DXY)", "group": "Rates & Dollar",
                        "role": "rates", "timing": "coincident", "unit": "index",
                        "progress": "lower", "source": "TradingView",
                        "description": "Dollar index; a stronger dollar tightens global liquidity."},

    # ---- Housing --------------------------------------------------------
    "housing.mortgage":     {"title": "30y mortgage rate", "group": "Housing",
                             "role": "housing", "timing": "leading", "unit": "%",
                             "progress": "lower", "source": "FRED:MORTGAGE30US",
                             "description": "30-year fixed mortgage rate."},
    "housing.xhb":          {"title": "Homebuilders ETF", "group": "Housing",
                             "role": "housing", "timing": "leading", "unit": "$",
                             "progress": "higher", "source": "TradingView",
                             "description": "Homebuilder equity proxy (XHB)."},
    "housing.permits_yoy":  {"title": "Building permits YoY", "group": "Housing",
                             "role": "housing", "timing": "leading", "unit": "% YoY",
                             "progress": "higher", "source": "FRED:PERMIT",
                             "description": "Building permits — leads housing starts and activity."},
    "housing.newsales_yoy": {"title": "New home sales YoY", "group": "Housing",
                             "role": "housing", "timing": "leading", "unit": "% YoY",
                             "progress": "higher", "source": "FRED",
                             "description": "New single-family home sales, year-on-year."},

    # ---- Credit ---------------------------------------------------------
    "credit.ci_standards": {"title": "C&I lending standards", "group": "Credit",
                            "role": "credit", "timing": "leading", "unit": "net % tightening",
                            "progress": "lower", "source": "FRED (SLOOS)",
                            "description": "Net share of banks tightening C&I standards; higher = tighter credit."},
    "credit.ci_demand":    {"title": "C&I loan demand", "group": "Credit",
                            "role": "credit", "timing": "leading", "unit": "net % stronger",
                            "progress": "higher", "source": "FRED (SLOOS)",
                            "description": "Net share of banks reporting stronger C&I loan demand."},
    "credit.totll_yoy":    {"title": "Total loans & leases YoY", "group": "Credit",
                            "role": "credit", "timing": "coincident", "unit": "% YoY",
                            "progress": "higher", "source": "FRED:TOTLL",
                            "description": "Bank loan growth, year-on-year."},

    # ---- China ----------------------------------------------------------
    "china.pboc":  {"title": "PBoC balance sheet", "group": "China",
                    "role": "china", "timing": "leading", "unit": "CNY (level)",
                    "progress": "higher", "source": "TradingView ECONOMICS:CNCBBS",
                    "description": "PBoC total assets — a China liquidity proxy."},
    "china.cn10y": {"title": "China 10y yield", "group": "China",
                    "role": "china", "timing": "coincident", "unit": "%",
                    "progress": "higher", "source": "TradingView TVC:CN10Y",
                    "description": "China 10-year government bond yield."},
}


def meta_for(path):
    """Return the meta dict for a dotted data.json leaf path, or a minimal
    fallback so an unregistered series still summarises (title = the path)."""
    return META.get(path) or {
        "title": path, "group": None, "role": None, "timing": None,
        "unit": None, "progress": "higher", "source": None, "description": None,
    }


if __name__ == "__main__":
    print(f"{len(META)} indicators registered")
    groups = {}
    for p, m in META.items():
        groups.setdefault(m["group"], []).append(p)
    for g, ps in groups.items():
        print(f"  {g}: {len(ps)}")
