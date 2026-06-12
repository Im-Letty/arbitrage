// scripts/snapshot.js
// Server-side judgment snapshot recorder for the arbitrage education app.
// Runs in GitHub Actions (Node 20). Uses the SINGLE-SOURCE judge.js shared with the browser.
// Fetches 5 symbols serially from Binance spot, runs arbiJudge, writes one row per symbol to Neon.

const { arbiJudge } = require('../judge.js');
const { Client } = require('pg');

// Public market-data host (data-api.binance.vision) is used instead of api.binance.com because
// api.binance.com geo-blocks many data-center IPs (e.g. GitHub Actions runners) with HTTP 451.
const API = "https://data-api.binance.vision";
const SYMS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT'];
const NAMES = { BTCUSDT: 'BTC', ETHUSDT: 'ETH', BNBUSDT: 'BNB', SOLUSDT: 'SOL', XRPUSDT: 'XRP' };

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

async function fetchSnapshot(sym) {
  const trRes = await fetchJson(API + "/api/v3/ticker/24hr?symbol=" + sym);
  const tr = trRes.data;
  if (!tr || typeof tr !== 'object' || Array.isArray(tr) || tr.lastPrice === undefined) {
    console.error("ticker unexpected for " + sym + " status=" + trRes.status + " body=" + trRes.bodyHead);
    throw new Error("ticker response not in expected shape");
  }
  const klRes = await fetchJson(API + "/api/v3/klines?symbol=" + sym + "&interval=1h&limit=24");
  const kl = klRes.data;
  if (!Array.isArray(kl)) {
    console.error("klines unexpected for " + sym + " status=" + klRes.status + " body=" + klRes.bodyHead);
    throw new Error("klines response not an array");
  }
  const closes = kl.map(function (k) { return parseFloat(k[4]); });
  return {
    symbol: NAMES[sym],
    price: tr.lastPrice,
    changePct: tr.priceChangePercent,
    high24: tr.highPrice,
    low24: tr.lowPrice,
    hourlyCloses: closes
  };
}

// Trend-half computation mirrors MARKET_HTML exactly (same formulas the browser uses to
// build snap.trendFirstHalf / snap.trendSecondHalf). Kept here because judge.js returns
// t1/t2 but the browser derives trendDir from these snapshot fields, not from judge.js.
function trendFirstHalf(closes) {
  if (!closes || closes.length < 4) return null;
  const h = Math.floor(closes.length / 2);
  const a = parseFloat(closes[0]), b = parseFloat(closes[h - 1]);
  if (a > 0) return (b - a) / a * 100;
  return null;
}
function trendSecondHalf(closes) {
  if (!closes || closes.length < 4) return null;
  const h = Math.floor(closes.length / 2);
  const a = parseFloat(closes[h]), b = parseFloat(closes[closes.length - 1]);
  if (a > 0) return (b - a) / a * 100;
  return null;
}
function trendDirFrom(tfh, tsh) {
  // Same threshold (0.1) as the browser (MARKET_HTML).
  if (typeof tfh === 'number' && typeof tsh === 'number') {
    const dd = tsh - tfh;
    if (dd > 0.1) return 'up';
    if (dd < -0.1) return 'down';
  }
  return 'neutral';
}

async function main() {
  const url = process.env.NEON_DATABASE_URL;
  if (!url) { console.error("NEON_DATABASE_URL is not set"); process.exit(1); }
  const client = new Client({ connectionString: url, ssl: { rejectUnauthorized: false } });
  await client.connect();
  try {
    await client.query(CREATE_SQL);
    for (const sym of SYMS) {
      try {
        const snap = await fetchSnapshot(sym);
        const r = arbiJudge(snap);
        const tfh = trendFirstHalf(snap.hourlyCloses);
        const tsh = trendSecondHalf(snap.hourlyCloses);
        const trendDir = trendDirFrom(tfh, tsh);
        const price = parseFloat(snap.price);
        const changePct = parseFloat(snap.changePct);
        await client.query(
          "INSERT INTO judge_records (ts, symbol, source, via, price, change_pct, mark, label, trend_dir, r1, r4, r24, conds) VALUES (now(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)",
          [
            snap.symbol,
            'binance-spot',
            'server',
            isFinite(price) ? price : null,
            isFinite(changePct) ? changePct : null,
            r.mark,
            r.label,
            trendDir,
            null,
            null,
            null,
            JSON.stringify(r.conds || [])
          ]
        );
        console.log("ok " + sym + " " + r.mark + " " + trendDir);
      } catch (e) {
        console.error("skip " + sym + ": " + (e && e.message ? e.message : e));
      }
    }
  } finally {
    await client.end();
  }
}

main().catch(function (e) { console.error(e); process.exit(1); });
