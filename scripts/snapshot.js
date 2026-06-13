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
// Binance base -> Kraken base alias (Kraken quirk: BTC is XBT). Others are same-named.
const KR_ALIAS = { BTC: "XBT" };

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
async function backfillResults(client) {
  const SELECT_SQL =
    "SELECT id, symbol, ts, price, horizon FROM (" +
    "  SELECT id, symbol, ts, price, '1' AS horizon FROM judge_records" +
    "   WHERE r1 IS NULL AND price IS NOT NULL AND ts + interval '1 hour' + interval '60 sec' < now()" +
    " UNION ALL " +
    "  SELECT id, symbol, ts, price, '4' AS horizon FROM judge_records" +
    "   WHERE r4 IS NULL AND price IS NOT NULL AND ts + interval '4 hours' + interval '60 sec' < now()" +
    " UNION ALL " +
    "  SELECT id, symbol, ts, price, '24' AS horizon FROM judge_records" +
    "   WHERE r24 IS NULL AND price IS NOT NULL AND ts + interval '24 hours' + interval '60 sec' < now()" +
    ") t ORDER BY ts ASC LIMIT 120";
  const rows = (await client.query(SELECT_SQL)).rows;
  let filled = 0, failed = 0;
  for (const row of rows) {
    try {
      const hours = row.horizon === "24" ? 24 : (row.horizon === "4" ? 4 : 1);
      const targetMs = new Date(row.ts).getTime() + hours * 3600 * 1000;
      const bucket = Math.floor(targetMs / 60000) * 60000;
      const klRes = await fetchJson(API + "/api/v3/klines?symbol=" + row.symbol + "&interval=1m&startTime=" + bucket + "&limit=1");
      const kl = klRes.data;
      if (!Array.isArray(kl) || !kl.length || !Array.isArray(kl[0])) { failed++; continue; }
      const close = parseFloat(kl[0][4]);
      const base = parseFloat(row.price);
      if (!isFinite(close) || !isFinite(base) || base === 0) { failed++; continue; }
      const pct = Math.round((close - base) / base * 100 * 1000) / 1000;
      const col = row.horizon === "24" ? "r24" : (row.horizon === "4" ? "r4" : "r1");
      const UPDATE_SQL = col === "r24"
        ? "UPDATE judge_records SET r24 = $1 WHERE id = $2"
        : (col === "r4"
          ? "UPDATE judge_records SET r4 = $1 WHERE id = $2"
          : "UPDATE judge_records SET r1 = $1 WHERE id = $2");
      await client.query(UPDATE_SQL, [pct, row.id]);
      filled++;
    } catch (e) {
      failed++;
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
      const reqList = picked.map(function (p) {
        const base = p.sym.slice(0, -4);
        const kbase = (KR_ALIAS[base] || base);
        return { sym: p.sym, kbase: kbase, krpair: kbase + "USD" };
      });
      const pairParam = reqList.map(function (x) { return x.krpair; }).join(",");
      const t0 = Date.now();
      const kr = await fetchJson(KRAKEN + "/0/public/Ticker?pair=" + pairParam);
      const ms = Date.now() - t0;
      const result = (kr && kr.data && kr.data.result) ? kr.data.result : null;
      const errs = (kr && kr.data && kr.data.error) ? kr.data.error : [];
      if (result && (!errs || errs.length === 0)) {
        // Normalize a Kraken canonical response key to a comparable base.
        // IMPORTANT: strip ZUSD before USD (every ...ZUSD also ends in USD), then drop a
        // leading class-prefix X for the 4-char XClass forms (XXBT->XBT, XETH->ETH, XXRP->XRP).
        const norm = function (key) {
          var k = key;
          if (k.slice(-4) === "ZUSD") k = k.slice(0, -4);
          else if (k.slice(-3) === "USD") k = k.slice(0, -3);
          if (k.length === 4 && k.charAt(0) === "X") k = k.slice(1);
          return k;
        };
        const keyByBase = {};
        Object.keys(result).forEach(function (key) { keyByBase[norm(key)] = key; });
        reqList.forEach(function (x) {
          const key = keyByBase[x.kbase];
          if (key && result[key] && result[key].c && result[key].c[0] != null) {
            const px = parseFloat(result[key].c[0]);
            if (isFinite(px) && px > 0) krMap[x.sym] = px;
          }
        });
      }
      console.log("kraken: status=" + (kr ? kr.status : "n/a") + " ms=" + ms + " matched=" + Object.keys(krMap).length + "/" + picked.length + (errs && errs.length ? (" err=" + JSON.stringify(errs)) : ""));
    } catch (e) {
      console.warn("kraken fetch failed (continuing with C1-C4 only): " + (e && e.message ? e.message : e));
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
        const r = arbiJudge(snap);
        const price = parseFloat(snap.price);
        const changePct = parseFloat(snap.changePct);
        await client.query(
          "INSERT INTO judge_records (ts, symbol, source, via, price, change_pct, mark, label, trend_dir, r1, r4, r24, conds, judge_ver, pick) VALUES (now(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, '3.0', $13)",
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
