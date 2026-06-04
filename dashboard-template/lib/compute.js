// ===========================================================================
//  COMPUTE MODULE  —  pure, framework-agnostic functions.
//  This is the dashboard's "brain": the frozen log-regression and the
//  buy/sell simulation. It has NO knowledge of React, Recharts, the data
//  source, or the DOM. Give it a price series + parameters, it returns numbers.
//
//  Because it is pure, it ships UNCHANGED from prototype to production. Nobody
//  re-implements the regression in Python and risks getting it subtly wrong —
//  the same tested function runs everywhere. It is also trivially unit-testable
//  (see the check-cases in SPEC_compounding-machine.md §8).
// ===========================================================================
(function (global) {
  "use strict";

  var DAY = 864e5;
  var WEEK = 604800000;

  // Parse a "YYYY-MM-DD" key to a millisecond timestamp (local midnight).
  function ts(d) {
    if (typeof d === "number") return d;
    var p = d.split("-");
    return new Date(+p[0], +p[1] - 1, +p[2]).getTime();
  }

  // Ordinary least squares: returns {a: intercept, b: slope}.
  function linReg(xs, ys) {
    var n = xs.length, sx = 0, sy = 0, sxy = 0, sx2 = 0;
    for (var i = 0; i < n; i++) {
      sx += xs[i]; sy += ys[i]; sxy += xs[i] * ys[i]; sx2 += xs[i] * xs[i];
    }
    var b = (n * sxy - sx * sy) / (n * sx2 - sx * sx);
    return { a: (sy - b * sx) / n, b: b };
  }

  // Fit the FROZEN log-linear trend on closes up to freezeDate.
  // Returns the regression coefficients + headline readouts. Once fit, these
  // numbers never move — that is what "frozen Dec '25" means.
  //   series: [{d, c}]   startDate/freezeDate: "YYYY-MM-DD"
  function fitFrozenRegression(series, opts) {
    var ref = ts(opts.startDate);
    var freeze = ts(opts.freezeDate);
    var fit = series.filter(function (p) { return ts(p.d) <= freeze; });
    if (fit.length < 10) return null;
    var xs = fit.map(function (p) { return (ts(p.d) - ref) / DAY; });
    var ly = fit.map(function (p) { return Math.log(p.c); });
    var r = linReg(xs, ly);
    var res = ly.map(function (l, i) { return l - (r.a + r.b * xs[i]); });
    var sd = Math.sqrt(res.reduce(function (s, e) { return s + e * e; }, 0) / res.length);
    return {
      a: r.a, b: r.b, sd: sd, ref: ref,
      impliedCAGR: Math.round((Math.exp(r.b * 365) - 1) * 100), // %/yr
      sd1pct: Math.round((Math.exp(sd) - 1) * 100)               // 1σ as a %
    };
  }

  // Build the price-vs-trend channel: historical points carry the real price;
  // forward points (to projectToYear) carry trend + bands only (NOT a forecast).
  function buildChannel(series, reg, opts) {
    var buyT = opts.buyThreshold, sellT = opts.sellThreshold;
    function pt(date, price, isProj) {
      var x = (date - reg.ref) / DAY;
      var tv = reg.a + reg.b * x;
      var base = {
        date: date, trend: Math.exp(tv),
        upper1: Math.exp(tv + reg.sd), lower1: Math.exp(tv - reg.sd),
        upper2: Math.exp(tv + 2 * reg.sd), lower2: Math.exp(tv - 2 * reg.sd),
        isProjection: isProj
      };
      if (isProj) {
        base.price = null; base.logDev = null;
        base.isOversold = false; base.isOverbought = false;
        return base;
      }
      base.price = price;
      base.logDev = (Math.log(price) - tv) / reg.sd;
      base.isOversold = price < Math.exp(tv - buyT * reg.sd);
      base.isOverbought = price > Math.exp(tv + sellT * reg.sd);
      return base;
    }
    var hist = series.map(function (p) { return pt(ts(p.d), p.c, false); });
    var lastDate = ts(series[series.length - 1].d);
    var end = new Date(opts.projectToYear, 0, 1).getTime();
    var proj = [];
    for (var t = lastDate + WEEK; t <= end; t += WEEK) proj.push(pt(t, null, true));
    return { hist: hist, proj: proj, all: hist.concat(proj), lastDate: lastDate };
  }

  // Run the strategy across the full history. Mirrors the prototype exactly:
  //  - fixed-dollar add each time price is oversold (with re-arming)
  //  - optional lifestyle-chip sell of sellPct of holdings when overbought
  //  - cash from sells is recycled into the next buys (reduces out-of-pocket)
  // Also runs the "no sells" pure-compounding path and the HODL baseline.
  function simulate(channel, reg, params) {
    var initialStake = params.initialStake,
        buyThreshold = params.buyThreshold,
        buyAmount = params.buyAmount,
        sellThreshold = params.sellThreshold,
        sellPct = params.sellPct;
    var all = channel.all;

    var units = initialStake / all[0].price, hodlUnits = units;
    var cash = 0, totalDeployed = initialStake, outOfPocket = initialStake, totalCashedOut = 0;
    var bArm = true, sArm = true;
    var buys = [], sells = [];

    var sim = all.map(function (d, i) {
      if (d.isProjection) return Object.assign({}, d, { strategy: null, hodl: null });
      if (!bArm && d.logDev > -buyThreshold / 2) bArm = true;
      if (!sArm && d.logDev < sellThreshold / 2) sArm = true;
      if (d.isOversold && bArm && i > 0) {
        var amt = buyAmount;
        totalDeployed += amt;
        if (cash >= amt) cash -= amt; else { outOfPocket += amt - cash; cash = 0; }
        units += amt / d.price; bArm = false;
        buys.push({ date: d.date, price: d.price, amount: amt, sv: units * d.price + cash });
      }
      if (d.isOverbought && sArm && i > 0) {
        var sell = units * (sellPct / 100), proc = sell * d.price;
        units -= sell; cash += proc; totalCashedOut += proc; sArm = false;
        sells.push({ date: d.date, price: d.price, amount: proc, sv: units * d.price + cash });
      }
      return Object.assign({}, d, { strategy: units * d.price + cash, hodl: hodlUnits * d.price });
    });

    // "No sells" pure-compounding path (adds at the lows, never trims).
    var pUnits = initialStake / all[0].price, pureCap = initialStake, pArm = true;
    var pure = all.map(function (d, i) {
      if (d.isProjection) return Object.assign({}, d, { pure: null });
      if (!pArm && d.logDev > -buyThreshold / 2) pArm = true;
      if (d.isOversold && pArm && i > 0) { pUnits += buyAmount / d.price; pureCap += buyAmount; pArm = false; }
      return Object.assign({}, d, { pure: pUnits * d.price });
    });

    var histSim = sim.filter(function (r) { return !r.isProjection; });
    var histPure = pure.filter(function (r) { return !r.isProjection; });
    var lhL = histSim[histSim.length - 1];
    var curS = lhL.strategy, curH = lhL.hodl, curPure = histPure[histPure.length - 1].pure;

    return {
      sim: sim, pure: pure, buys: buys, sells: sells,
      stats: {
        totalDeployed: totalDeployed, outOfPocket: outOfPocket, totalCashedOut: totalCashedOut,
        cash: cash, curS: curS, curH: curH, btcVal: curS - cash, curPure: curPure, pureCap: pureCap
      }
    };
  }

  // Convenience: the whole pipeline in one call, returning everything the
  // shell needs to render. Keeps the shell dumb (render only, no maths).
  function analyse(series, params) {
    if (!series || series.length < 10) return null;
    var reg = fitFrozenRegression(series, params);
    if (!reg) return null;
    var channel = buildChannel(series, reg, params);
    var run = simulate(channel, reg, params);
    var hist = channel.hist;
    var last = hist[hist.length - 1];
    return {
      reg: reg, channel: channel, run: run,
      currentSigma: last.logDev, trendNow: last.trend,
      lastPrice: series[series.length - 1].c, lastDate: channel.lastDate
    };
  }

  var api = { linReg: linReg, fitFrozenRegression: fitFrozenRegression,
              buildChannel: buildChannel, simulate: simulate, analyse: analyse };

  if (typeof module !== "undefined" && module.exports) module.exports = api; // node / tests
  global.GMI_COMPUTE = api;                                                  // browser shell
})(typeof window !== "undefined" ? window : globalThis);
