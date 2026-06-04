// ===========================================================================
//  SOURCES  —  the asset registry + the data-source "socket".
//
//  THIS is the file that makes the dashboard portable across data providers.
//  The shell never talks to a data provider directly. It asks ONE function,
//  getAssetSeries(key), for a standard series of { d:"YYYY-MM-DD", c:number }.
//  That function dispatches to an ADAPTER chosen per-asset in ASSET_REGISTRY.
//
//  Swapping providers = change the `source` field on an asset, or add a new
//  adapter below. The dashboard, the compute module, and the render code never
//  change. (This is the seam that lets a team plug in their own internal feed
//  instead of TradingView, and the reason "we can't use NDX" is a one-line
//  config edit, not a rewrite.)
// ===========================================================================
(function (global) {
  "use strict";

  // ---- ASSET REGISTRY ------------------------------------------------------
  // One row per asset. To remove an asset (e.g. NDX licensing): delete its row.
  // To add one: copy a row, set the ticker, the source, and its frozen params.
  // To re-point an asset at a different provider: change `source` (+ symbol).
  var ASSET_REGISTRY = [
    {
      key: "BTC", name: "Bitcoin", ticker: "BTC", unit: "BTC", color: "#F6C343",
      source: "injected",            // <- swap to "coingecko" for live, or "internal" for your feed
      symbol: "INDEX:BTCUSD",        // provider symbol (used by live adapters)
      projectToYear: 2035            // how far the forward channel extends
    },
    {
      key: "NDX", name: "Nasdaq 100", ticker: "NDX", unit: "units", color: "#60A5FA",
      source: "injected",            // NDX stays on injected/pipeline data (no public live feed)
      symbol: "NASDAQ:NDX",
      proxyTicker: "QQQ",            // ETF proxy for live tip (beta); native build uses RV's QQQ feed
      projectToYear: 2030
    }
  ];

  // Map any millisecond time to that week's Friday key "YYYY-MM-DD" (the tool's
  // weekly anchor). Shared by the live adapters so a live tip lands on the same
  // weekly grid as the embedded history.
  function fridayKey(ms) {
    var dt = new Date(ms), day = dt.getUTCDay();
    var fri = Date.UTC(dt.getUTCFullYear(), dt.getUTCMonth(), dt.getUTCDate() + ((5 - day + 7) % 7));
    var k = new Date(fri);
    return k.getUTCFullYear() + "-" + String(k.getUTCMonth() + 1).padStart(2, "0") + "-" + String(k.getUTCDate()).padStart(2, "0");
  }
  function embeddedSeries(asset) {
    return (((global.DASHBOARD_DATA || {}).assets || {})[asset.key] || {}).series || [];
  }
  // Fetch JSON through a public CORS proxy so a browser can reach feeds (like
  // Yahoo) that refuse keyless cross-origin requests directly. Tries two free
  // proxies, then gives up (caller falls back to demo). Beta-only crutch.
  function proxiedJson(targetUrl) {
    var a = "https://api.allorigins.win/raw?url=" + encodeURIComponent(targetUrl);
    var b = "https://corsproxy.io/?url=" + encodeURIComponent(targetUrl);
    return fetch(a).then(function (r) { if (!r.ok) throw 0; return r.json(); })
      .catch(function () { return fetch(b).then(function (r) { if (!r.ok) throw 0; return r.json(); }); });
  }

  // Append/replace today's live price as the current weekly point on top of the
  // embedded history. Keeps the frozen regression (built on history) intact.
  function withLiveTip(base, price, src) {
    if (!(price > 0)) return { series: base, live: false, src: "demo" };
    var out = base.slice(), k = fridayKey(Date.now());
    if (out.length && out[out.length - 1].d === k) out[out.length - 1] = { d: k, c: price };
    else out.push({ d: k, c: price });
    return { series: out, live: true, src: src };
  }

  // ---- ADAPTERS ------------------------------------------------------------
  // Every adapter returns a Promise of [{ d:"YYYY-MM-DD", c:number }, ...].
  // That uniform shape is the whole contract. Add providers here.
  //
  // FOR A PLATFORM BUILD: use `injected` or `platform` only. Both keep data
  // INSIDE Real Vision's platform — no external provider is contacted at
  // runtime. The `coingecko` adapter is an illustrative example of the socket
  // accepting any provider; delete it for production.
  var ADAPTERS = {

    // DEFAULT, production-aligned path: read the weekly series the platform
    // pipeline already wrote into data/data.js. This mirrors how the live
    // Everything Code dashboard reads window.TGL_DATA from data/data.js.
    // Nothing leaves the platform — the series is pre-supplied, not fetched.
    injected: function (asset) {
      var d = (global.DASHBOARD_DATA || {}).assets || {};
      var s = d[asset.key] && d[asset.key].series;
      return Promise.resolve(s || []);
    },

    // INTENDED PRODUCTION PATH for live data: fetch the weekly series from Real
    // Vision's own in-platform data service. Stub below — P&E wires the real
    // endpoint/shared-data client and maps the response to [{d,c}]. The rest of
    // the dashboard does not change. This is the answer to "it can't reference
    // data outside our platform": point this at the platform and it never does.
    platform: function (asset) {
      // e.g. return RVData.weeklyCloses(asset.symbol).then(rows =>
      //        rows.map(r => ({ d: r.date, c: r.close })));
      return Promise.reject(new Error("platform adapter not wired yet"));
    },

    // BETA-ONLY, external — remove for platform builds. Takes the embedded
    // weekly history as the base and refreshes the current price from a keyless,
    // browser-safe, US-reachable source (Coinbase spot, with Kraken as backup).
    // It does NOT use CoinGecko's historical endpoint, which now needs a paid key
    // (that was why the old build silently fell back to stale data). Returns
    // { series, live, src } so the UI can label honestly: "LIVE" only when the
    // feed actually answered, otherwise an honest "DEMO · as-of <date>".
    live: function (asset) {
      var base = embeddedSeries(asset);
      // Primary: Coinbase (keyless, CORS, US-friendly). Backup: Kraken.
      return fetch("https://api.coinbase.com/v2/prices/BTC-USD/spot")
        .then(function (r) { if (!r.ok) throw 0; return r.json(); })
        .then(function (j) { return parseFloat(j.data.amount); })
        .catch(function () {
          return fetch("https://api.kraken.com/0/public/Ticker?pair=XBTUSD")
            .then(function (r) { return r.json(); })
            .then(function (j) { return parseFloat(j.result.XXBTZUSD.c[0]); });
        })
        .then(function (price) { return withLiveTip(base, price, "coinbase"); })
        .catch(function () { return { series: base, live: false, src: "demo" }; });
    },

    // BETA-ONLY, external, BEST-EFFORT — refresh an index's current level using
    // its ETF proxy (e.g. QQQ for NDX), the same proxy the team uses. Index/ETF
    // quotes need a CORS proxy to reach a browser keyless, so this is fragile;
    // on any failure it falls back to honest demo. The RELIABLE answer is the
    // platform adapter (RV's QQQ end-of-day feed, which they already have).
    //
    // QQQ trades ~$500 while NDX history is in index units (~24,000), so we
    // calibrate the scale: ratio = NDX(last embedded) / QQQ(close near that
    // date), then NDX_now ≈ QQQ_now × ratio. This keeps the line continuous.
    qqqProxy: function (asset) {
      var base = embeddedSeries(asset);
      if (!base.length) return Promise.resolve({ series: base, live: false, src: "demo" });
      var last = base[base.length - 1], lastMs = Date.parse(last.d);
      var yurl = "https://query1.finance.yahoo.com/v8/finance/chart/" + (asset.proxyTicker || "QQQ") + "?range=3mo&interval=1d";
      return proxiedJson(yurl).then(function (j) {
        var res = j.chart.result[0], ts = res.timestamp, cl = res.indicators.quote[0].close;
        var qAnchor = null, bestDiff = Infinity, qNow = null;
        for (var i = 0; i < ts.length; i++) {
          if (cl[i] == null) continue;
          var diff = Math.abs(ts[i] * 1000 - lastMs);
          if (diff < bestDiff) { bestDiff = diff; qAnchor = cl[i]; }
          qNow = cl[i];                                  // ascending → last non-null is latest
        }
        if (!(qAnchor > 0) || !(qNow > 0)) throw 0;
        var ratio = last.c / qAnchor;                    // QQQ → NDX-units scale at the splice
        return withLiveTip(base, qNow * ratio, "qqq→ndx");
      }).catch(function () { return { series: base, live: false, src: "demo" }; });
    }

    // internal: function (asset) { ... }   // <- a team drops their own feed in here.
    //   Must return Promise<[{d:"YYYY-MM-DD", c:number}]>. Nothing else changes.
  };

  // ---- THE ONE ENTRY POINT THE SHELL USES ---------------------------------
  // Falls back to the injected data if a live adapter errors, so the dashboard
  // degrades gracefully instead of going blank (same spirit as the pipeline's
  // "skip the asset, keep the rest" resilience).
  function getAssetSeries(key) {
    var asset = ASSET_REGISTRY.filter(function (a) { return a.key === key; })[0];
    if (!asset) return Promise.resolve({ series: [], source: "missing", live: false, asset: null });
    var adapter = ADAPTERS[asset.source] || ADAPTERS.injected;
    var asOf = (global.DASHBOARD_DATA || {}).updated || "";
    function injectedFallback() {
      return ADAPTERS.injected(asset).then(function (s) {
        return { series: s, source: "injected", live: false, asOf: asOf, asset: asset };
      });
    }
    return Promise.resolve(adapter(asset)).then(function (out) {
      // Adapters return either a bare series array or { series, live, src }.
      var series = Array.isArray(out) ? out : (out && out.series);
      var live = Array.isArray(out) ? false : !!(out && out.live);
      var src = Array.isArray(out) ? asset.source : ((out && out.src) || asset.source);
      if (series && series.length > 10) return { series: series, source: src, live: live, asOf: asOf, asset: asset };
      return injectedFallback();
    }).catch(injectedFallback);
  }

  global.GMI_SOURCES = {
    ASSET_REGISTRY: ASSET_REGISTRY,
    ADAPTERS: ADAPTERS,
    getAssetSeries: getAssetSeries
  };
})(typeof window !== "undefined" ? window : globalThis);
