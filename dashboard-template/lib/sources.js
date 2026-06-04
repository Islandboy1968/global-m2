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
      projectToYear: 2030
    }
  ];

  // ---- ADAPTERS ------------------------------------------------------------
  // Every adapter returns a Promise of [{ d:"YYYY-MM-DD", c:number }, ...].
  // That uniform shape is the whole contract. Add providers here.
  var ADAPTERS = {

    // DEFAULT, production-aligned path: read the weekly series the pipeline
    // already wrote into data/data.js. This mirrors how the live Everything
    // Code dashboard reads window.TGL_DATA from data/data.js.
    injected: function (asset) {
      var d = (global.DASHBOARD_DATA || {}).assets || {};
      var s = d[asset.key] && d[asset.key].series;
      return Promise.resolve(s || []);
    },

    // EXAMPLE live adapter (BTC only) — demonstrates a genuinely different
    // provider behind the same socket. Builds Friday-anchored weekly closes
    // from CoinGecko's daily prices, exactly like the original prototype.
    coingecko: function (asset) {
      var url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=3200&interval=daily";
      var START = new Date(2017, 8, 1).getTime();
      return fetch(url).then(function (r) {
        if (!r.ok) throw new Error("coingecko " + r.status);
        return r.json();
      }).then(function (j) {
        var byWeek = {};
        j.prices.forEach(function (row) {
          var t = row[0], p = row[1];
          if (t < START) return;
          var dt = new Date(t), day = dt.getUTCDay();
          var fri = Date.UTC(dt.getUTCFullYear(), dt.getUTCMonth(), dt.getUTCDate() + ((5 - day + 7) % 7));
          var k = new Date(fri);
          var key = k.getUTCFullYear() + "-" + String(k.getUTCMonth() + 1).padStart(2, "0") + "-" + String(k.getUTCDate()).padStart(2, "0");
          byWeek[key] = p; // last write in the week wins
        });
        return Object.keys(byWeek).sort().map(function (k) { return { d: k, c: byWeek[k] }; });
      });
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
    if (!asset) return Promise.resolve({ series: [], source: "missing", asset: null });
    var adapter = ADAPTERS[asset.source] || ADAPTERS.injected;
    return adapter(asset).then(function (series) {
      if (series && series.length > 10) return { series: series, source: asset.source, asset: asset };
      return ADAPTERS.injected(asset).then(function (s) { return { series: s, source: "injected", asset: asset }; });
    }).catch(function () {
      return ADAPTERS.injected(asset).then(function (s) { return { series: s, source: "injected", asset: asset }; });
    });
  }

  global.GMI_SOURCES = {
    ASSET_REGISTRY: ASSET_REGISTRY,
    ADAPTERS: ADAPTERS,
    getAssetSeries: getAssetSeries
  };
})(typeof window !== "undefined" ? window : globalThis);
