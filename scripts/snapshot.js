// scripts/snapshot.js
// Server-side judgment snapshot recorder for the arbitrage education app.
// Runs in GitHub Actions (Node 20). Uses the SINGLE-SOURCE judge.js shared with the browser.
// Selects the top-N USDT spot pairs by 24h quote volume each run, runs arbiJudge,
// and writes one row per selected symbol to Neon.
// C5 (cross-exchange divergence, jv3.0+): server-only. This script fetches Kraken USD prices once
//   and attaches snap.kr={price,dev} so arbiJudge adds a C5 cond. The BROWSER never sets snap.kr,
//   so browser records carry C1-C4 only while server records may carry C1-C5. The aggregation side
//   (app.py board / B-3) treats C5 as OPTIONAL, so the differing conds composition mixes safely.

const { arbiJudge } = require('../judge.js');
const { Client } = require('pg');

// Public market-data host (data-api.binance.vision) is used instead of api.binance.com because
// api.binance.com geo-blocks many data-center IPs (e.g. GitHub Actions runners) with HTTP 451.
const API = "https://data-api.binance.vision";

// Number of top-volume symbols to record each run. Bump this to widen coverage.
const TOP_N = 20;

// Event promotion slots: in addition to the always-on top-volume set, temporarily promote
// symbols that are "having an event" (large 24h move) but are not in the top TOP_N.
// No extra API calls: reuse the single ticker list already fetched by selectTickers().
const EVENT_CHG = 10;   // promote when abs(priceChangePercent) >= this (percent)
const EVENT_MAX = 10;   // max number of promoted symbols per run

// C5 cross-exchange divergence (server-only). Compare Binance USDT-spot vs Kraken USD price.
// Design case C: NO normalization; the 0.15 C5 threshold (judge.js) absorbs the ~0.06% USDT/USD peg noise.
// Kraken USD coverage is much wider than USDT, so we query USD pairs. Symbols absent on Kraken simply
// get no snap.kr (=> C1-C4 only = backward compatible). One bulk Ticker call per run (no per-symbol calls).
const KRAKEN = "https://api.kraken.com";
const BITGET = "https://api.bitget.com";
// Binance base -> Kraken base alias (Kraken quirk: BTC is XBT). Others are same-named.
const KR_ALIAS = { BTC: "XBT", DOGE: "XDG" };

// Stablecoin bases: a USDT pair whose base is itself a stablecoin (e.g. USDCUSDT) is excluded,
// because stable-vs-stable pairs are not meaningful for this educational arbitrage signal.
const STABLES = new Set(['USDC', 'FDUSD', 'TUSD', 'DAI', 'BUSD', 'USDP', 'UST', 'USDD', 'PYUSD', 'EUR', 'USD1', 'RLUSD', 'U', 'USDE', 'GUSD', 'USDS', 'FRAX', 'LUSD', 'AEUR']);

// Leveraged tokens (e.g. BTCUPUSDT, ETHDOWNUSDT, ...BULL/...BEAR) are excluded.
const LEV_RE = /(UP|DOWN|BULL|BEAR)$/;

const CREATE_SQL = `
CREATE TABLE IF NOT EXISTS judge_records (
  id bigserial PRIMARY KEY,
  ts timestamptz,
  symbol text,
  source text,
  via text,
  price double precision,
  change_pct double precision,
  mark text,
  label text,
  trend_dir text,
  r1 double precision,
  r4 double precision,
  r24 double precision,
  conds jsonb,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS judge_records_symbol_ts_idx ON judge_records (symbol, ts);
`;

// Fetch JSON and, when the shape is unexpected, surface a diagnostic (HTTP status + body head).
async function fetchJson(url) {
  const res = await fetch(url);
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch (e) { data = null; }
  return { status: res.status, ok: res.ok, data: data, bodyHead: text.slice(0, 200) };
}

// Pull the full 24hr ticker list once, filter to spot USDT pairs (excluding stablecoin-vs-stable
// and leveraged tokens), sort by quote volume desc, and keep the top TOP_N ticker objects.
async function selectTickers() {
  const res = await fetchJson(API + "/api/v3/ticker/24hr");
  const all = res.data;
  if (!Array.isArray(all)) {
    console.error("ticker list unexpected status=" + res.status + " body=" + res.bodyHead);
    throw new Error("ticker list not an array");
  }
  const cand = [];
  for (const it of all) {
    const sym = it && it.symbol;
    if (!sym || sym.slice(-4) !== "USDT") continue;
    const base = sym.slice(0, -4);
    if (STABLES.has(base)) continue;
    if (LEV_RE.test(base)) continue;
    const qv = parseFloat(it.quoteVolume);
    if (!isFinite(qv)) continue;
    cand.push({ it: it, sym: sym, qv: qv });
  }
  cand.sort(function (a, b) { return b.qv - a.qv; });
  return cand;
}

// Fetch the 24x1h closes for one symbol. Ticker fields come from the already-fetched list item.
async function fetchCloses(sym) {
  const klRes = await fetchJson(API + "/api/v3/klines?symbol=" + sym + "&interval=1h&limit=24");
  const kl = klRes.data;
  if (!Array.isArray(kl)) {
    console.error("klines unexpected for " + sym + " status=" + klRes.status + " body=" + klRes.bodyHead);
    throw new Error("klines response not in expected shape");
  }
  return kl.map(function (k) { return parseFloat(k[4]); });
}

// Second job (case A): fill in r1/r4/r24 once the target time (ts+Nh) + 60s has passed,
// using the same data-api.binance.vision spot source as the original record. Browser-side
// arbiFillResults (localStorage) is intentionally left untouched: server fills server rows.
async function markFail(client, id) {
  try { await client.query("UPDATE judge_records SET fail_n = COALESCE(fail_n,0)+1, give_up = (COALESCE(fail_n,0)+1 >= 3) WHERE id = $1", [id]); } catch (e) {}
}
async function backfillResults(client) {
  const SELECT_SQL =
    "SELECT id, symbol, ts, price, horizon FROM (" +
    "  SELECT id, symbol, ts, price, '1' AS horizon FROM judge_records" +
    "   WHERE r1 IS NULL AND (give_up IS NULL OR give_up = false) AND price IS NOT NULL AND ts + interval '1 hour' + interval '60 sec' < now()" +
    " UNION ALL " +
    "  SELECT id, symbol, ts, price, '4' AS horizon FROM judge_records" +
    "   WHERE r4 IS NULL AND (give_up IS NULL OR give_up = false) AND price IS NOT NULL AND ts + interval '4 hours' + interval '60 sec' < now()" +
    " UNION ALL " +
    "  SELECT id, symbol, ts, price, '24' AS horizon FROM judge_records" +
    "   WHERE r24 IS NULL AND (give_up IS NULL OR give_up = false) AND price IS NOT NULL AND ts + interval '24 hours' + interval '60 sec' < now()" +
    ") t ORDER BY horizon::int ASC, ts ASC LIMIT 300";
  const rows = (await client.query(SELECT_SQL)).rows;
  let filled = 0, failed = 0;
  for (const row of rows) {
    try {
      const hours = row.horizon === "24" ? 24 : (row.horizon === "4" ? 4 : 1);
      const targetMs = new Date(row.ts).getTime() + hours * 3600 * 1000;
      const bucket = Math.floor(targetMs / 60000) * 60000;
      const klRes = await fetchJson(API + "/api/v3/klines?symbol=" + row.symbol + "&interval=1m&startTime=" + bucket + "&limit=1");
      const kl = klRes.data; if (klRes.status === 429) { continue; }
      if (!Array.isArray(kl) || !kl.length || !Array.isArray(kl[0])) { await markFail(client, row.id); failed++; continue; }
      const close = parseFloat(kl[0][4]);
      const base = parseFloat(row.price);
      if (!isFinite(close) || !isFinite(base) || base === 0) { await markFail(client, row.id); failed++; continue; }
      const pct = Math.round((close - base) / base * 100 * 1000) / 1000;
      const col = row.horizon === "24" ? "r24" : (row.horizon === "4" ? "r4" : "r1");
      const UPDATE_SQL = col === "r24"
        ? "UPDATE judge_records SET r24 = $1 WHERE id = $2"
        : (col === "r4"
          ? "UPDATE judge_records SET r4 = $1 WHERE id = $2"
          : "UPDATE judge_records SET r1 = $1 WHERE id = $2");
      await client.query(UPDATE_SQL, [pct, row.id]);
      filled++;
        try { await client.query("UPDATE judge_records SET fail_n = 0 WHERE id = $1", [row.id]); } catch (e) {}
    } catch (e) {
      await markFail(client, row.id); failed++;
    }
  }
  console.log("backfill: candidates=" + rows.length + " filled=" + filled + " failed=" + failed);
}

async function main() {
  const url = process.env.NEON_DATABASE_URL;
  if (!url) { console.error("NEON_DATABASE_URL is not set"); process.exit(1); }
  const client = new Client({ connectionString: url, ssl: { rejectUnauthorized: false } });
  await client.connect();
  try {
    await client.query(CREATE_SQL);
    await client.query("ALTER TABLE judge_records ADD COLUMN IF NOT EXISTS judge_ver text");
    await client.query("ALTER TABLE judge_records ADD COLUMN IF NOT EXISTS pick text");
    await client.query("ALTER TABLE judge_records ADD COLUMN IF NOT EXISTS give_up boolean DEFAULT false");
    await client.query("ALTER TABLE judge_records ADD COLUMN IF NOT EXISTS fail_n int DEFAULT 0");
    const cand = await selectTickers();
    const topSet = cand.slice(0, TOP_N).map(function (c) { c.pick = "top"; return c; });
    const topSyms = new Set(topSet.map(function (c) { return c.sym; }));
    const events = cand
      .filter(function (c) { return !topSyms.has(c.sym) && Math.abs(parseFloat(c.it.priceChangePercent)) >= EVENT_CHG; })
      .sort(function (a, b) { return Math.abs(parseFloat(b.it.priceChangePercent)) - Math.abs(parseFloat(a.it.priceChangePercent)); })
      .slice(0, EVENT_MAX)
      .map(function (c) { c.pick = "event"; return c; });
    const picked = topSet.concat(events);
    console.log("picked top=" + topSet.length + " event=" + events.length + (events.length ? " [" + events.map(function (c) { return c.sym; }).join(",") + "]" : ""));
    // --- C5: one bulk Kraken USD price fetch for all picked symbols (server-only) ---
    const krMap = {};
    try {
      // Build the candidate base list from picked symbols (Binance base -> Kraken base alias).
      let reqList = picked.map(function (p) {
        const base = p.sym.slice(0, -4);
        const kbase = (KR_ALIAS[base] || base);
        return { sym: p.sym, kbase: kbase, krpair: null };
      });
      // Case A: fetch Kraken's real AssetPairs once and keep only USD pairs that actually exist.
      // This prevents one unknown symbol from poisoning the whole Ticker batch (Kraken is all-or-nothing).
      const ap = await fetchJson(KRAKEN + "/0/public/AssetPairs");
      const apResult = (ap && ap.data && ap.data.result) ? ap.data.result : null;
      const apErrs = (ap && ap.data && ap.data.error) ? ap.data.error : [];
      // Normalize a Kraken base/asset code to a comparable base (strip leading class-prefix X on 4-char XClass codes).
      const normBase = function (b) { return (b && b.length === 4 && b.charAt(0) === "X") ? b.slice(1) : b; };
      const validByBase = {};
      if (apResult && (!apErrs || apErrs.length === 0)) {
        // Map normalized base -> { altname, tickerKey } for pairs quoted in USD (quote ZUSD or USD).
        Object.keys(apResult).forEach(function (key) {
          const info = apResult[key];
          if (!info) return;
          const quote = info.quote;
          if (quote !== "ZUSD" && quote !== "USD") return;
          const nb = normBase(info.base);
          // Prefer the altname for the Ticker request; remember the canonical key for response lookup.
          if (nb && !validByBase[nb]) validByBase[nb] = { altname: info.altname || key, tickerKey: key };
        });
      }
      // Keep only picked symbols whose Kraken base exists as a USD pair.
      reqList = reqList.filter(function (x) {
        const v = validByBase[x.kbase];
        if (!v) return false;
        x.krpair = v.altname; x.tickerKey = v.tickerKey;
        return true;
      });
      const validCount = Object.keys(validByBase).length;
      // Fallback: if AssetPairs failed/empty, skip Kraken entirely (all symbols get C1-C4 only).
      // Also skip the Ticker call if no picked symbol resolved to a real Kraken USD pair.
      let kr = null, ms = 0, result = null, errs = [];
      if (validCount > 0 && reqList.length > 0) {
        const pairParam = reqList.map(function (x) { return x.krpair; }).join(",");
        const t0 = Date.now();
        kr = await fetchJson(KRAKEN + "/0/public/Ticker?pair=" + pairParam);
        ms = Date.now() - t0;
        result = (kr && kr.data && kr.data.result) ? kr.data.result : null;
        errs = (kr && kr.data && kr.data.error) ? kr.data.error : [];
      } else {
        console.log("kraken: skipped (assetpairs valid=" + validCount + ", resolved=" + reqList.length + ")" + (apErrs && apErrs.length ? (" apErr=" + JSON.stringify(apErrs)) : ""));
      }
      if (result && (!errs || errs.length === 0)) {
        // Match each requested symbol to its Kraken price using the canonical key learned from
        // AssetPairs (x.tickerKey). If Kraken's Ticker echoes a slightly different key, fall back
        // to the altname or a direct scan. This avoids base-code mismatches (e.g. DOGE base is XDG).
        reqList.forEach(function (x) {
          var entry = result[x.tickerKey] || result[x.krpair];
          if (!entry) {
            // Last resort: find any result key whose stripped-USD form equals the altname's stripped form.
            var want = (x.krpair || "").replace(/USD$/, "");
            var hit = Object.keys(result).filter(function (k) {
              var kk = k.replace(/ZUSD$/, "").replace(/USD$/, "");
              if (kk.length === 4 && kk.charAt(0) === "X") kk = kk.slice(1);
              return kk === want;
            })[0];
            if (hit) entry = result[hit];
          }
          if (entry && entry.c && entry.c[0] != null) {
            var px = parseFloat(entry.c[0]);
            if (isFinite(px) && px > 0) krMap[x.sym] = px;
          }
        });
      }
      console.log("kraken: status=" + (kr ? kr.status : "n/a") + " ms=" + ms + " matched=" + Object.keys(krMap).length + "/" + picked.length + (errs && errs.length ? (" err=" + JSON.stringify(errs)) : ""));
    } catch (e) {
      console.warn("kraken fetch failed (continuing with C1-C4 only): " + (e && e.message ? e.message : e));
    }
    // C8/C9: one bulk Bybit linear (USDT perp) fetch for all symbols (server-only, v4).
    // /v5/market/tickers?category=linear returns every perp in one call; symbol is BTCUSDT form (same as picked.sym),
    // so NO pre-filter/alias step is needed (unlike Kraken). Build futMap[symbol]={fr,oi,oiUsd,mark}.
    // On any failure, futMap stays empty => every symbol gets C1-C5 only (pre-v4 output, fully backward compatible).
    // C6: one bulk Binance bookTicker fetch for all symbols (server-only, v5).
    // /api/v3/ticker/bookTicker (no symbol) returns best bid/ask for every symbol in one call,
    // via the same US-safe data-api.binance.vision host (api.binance.com is 451). +1 call only.
    // btMap[symbol] = spread% = (ask-bid)/((ask+bid)/2)*100, only when bid>0 && ask>0 (empty/halted books skipped).
    // On any failure, btMap stays empty => no C6 for any symbol (pre-v5 output, fully backward compatible).
    const btMap = {};
    try {
      const bt = await fetchJson(API + "/api/v3/ticker/bookTicker");
      const btList = (bt && bt.data && Array.isArray(bt.data)) ? bt.data : null;
      if (btList) {
        btList.forEach(function (x) {
          if (!x || !x.symbol) return;
          const bid = parseFloat(x.bidPrice);
          const ask = parseFloat(x.askPrice);
          if (!isFinite(bid) || !isFinite(ask) || bid <= 0 || ask <= 0) return;
          const sp = (ask - bid) / ((ask + bid) / 2) * 100;
          if (isFinite(sp) && sp >= 0) btMap[x.symbol] = sp;
        });
      }
      console.log("bookticker: status=" + (bt ? bt.status : "n/a") + " books=" + Object.keys(btMap).length);
    } catch (e) {
      console.warn("bookticker fetch failed (continuing without C6): " + (e && e.message ? e.message : e));
    }
          const futMap = {};
      try {
        const bg = await fetchJson(BITGET + "/api/v2/mix/market/tickers?productType=usdt-futures");
        const bgList = (bg && bg.data && Array.isArray(bg.data.data)) ? bg.data.data : null;
        if (bgList) {
          bgList.forEach(function (x) {
            if (!x || !x.symbol) return;
            const fr = parseFloat(x.fundingRate);
            const oi = parseFloat(x.holdingAmount);
            const mark = parseFloat(x.markPrice);
            const oiUsd = (isFinite(oi) && isFinite(mark)) ? oi * mark : NaN;
            const f = {};
            if (isFinite(fr)) f.fr = fr;
            if (isFinite(oi)) f.oi = oi;
            if (isFinite(oiUsd)) f.oiUsd = oiUsd;
            if (isFinite(mark)) f.mark = mark;
            futMap[x.symbol] = f;
          });
        }
        console.log("bitget-fut: status=" + (bg ? bg.status : "n/a") + " perps=" + Object.keys(futMap).length);
      } catch (e) {
        console.warn("bitget-fut fetch failed (continuing with C1-C6 only): " + (e && e.message ? e.message : e));
      }
    for (const p of picked) {
      const sym = p.sym;
      const it = p.it;
      try {
        const closes = await fetchCloses(sym);
        const snap = {
          symbol: sym,
          price: it.lastPrice,
          changePct: it.priceChangePercent,
          high24: it.highPrice,
          low24: it.lowPrice,
          hourlyCloses: closes
        };
        // C5: attach Kraken cross-exchange divergence only when a Kraken USD price was obtained.
        // dev% = (Kraken USD - Binance USDT) / Binance USDT * 100. Case C: no peg normalization.
        const __krPx = krMap[sym];
        const __biPx = parseFloat(it.lastPrice);
        if (typeof __krPx === "number" && isFinite(__krPx) && isFinite(__biPx) && __biPx > 0) {
          snap.kr = { price: __krPx, dev: (__krPx - __biPx) / __biPx * 100 };
        }
        // C8/C9: attach Bybit perp data only when this symbol has a Bybit linear perp (futMap hit).
        const __fut = futMap[sym];
        if (__fut && Object.keys(__fut).length > 0) { snap.fut = __fut; }
        // C6: attach order-book spread% only when this symbol had a valid book (btMap hit).
        const __sp = btMap[sym];
        if (typeof __sp === "number" && isFinite(__sp)) { snap.spread = __sp; }
        const r = arbiJudge(snap);
        const price = parseFloat(snap.price);
        const changePct = parseFloat(snap.changePct);
        await client.query(
          "INSERT INTO judge_records (ts, symbol, source, via, price, change_pct, mark, label, trend_dir, r1, r4, r24, conds, judge_ver, pick) VALUES (now(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, '5.0', $13)",
          [
            snap.symbol,
            'binance-spot',
            'server',
            isFinite(price) ? price : null,
            isFinite(changePct) ? changePct : null,
            r.mark,
            r.label,
            r.trendDir,
            null,
            null,
            null,
            JSON.stringify(r.conds || []),
            p.pick
          ]
        );
        console.log("ok " + sym + " " + r.mark + " " + r.trendDir);
      } catch (e) {
        console.error("skip " + sym + ": " + (e && e.message ? e.message : e));
      }
    }
    await backfillResults(client);
  } finally {
    await client.end();
  }
}

main().catch(function (e) { console.error(e); process.exit(1); });
