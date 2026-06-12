// scripts/snapshot.js
// Server-side judgment snapshot recorder for the arbitrage education app.
// Runs in GitHub Actions (Node 20). Uses the SINGLE-SOURCE judge.js shared with the browser.
// Selects the top-N USDT spot pairs by 24h quote volume each run, runs arbiJudge,
// and writes one row per selected symbol to Neon.

const { arbiJudge } = require('../judge.js');
const { Client } = require('pg');

// Public market-data host (data-api.binance.vision) is used instead of api.binance.com because
// api.binance.com geo-blocks many data-center IPs (e.g. GitHub Actions runners) with HTTP 451.
const API = "https://data-api.binance.vision";

// Number of top-volume symbols to record each run. Bump this to widen coverage.
const TOP_N = 20;

// Stablecoin bases: a USDT pair whose base is itself a stablecoin (e.g. USDCUSDT) is excluded,
// because stable-vs-stable pairs are not meaningful for this educational arbitrage signal.
const STABLES = new Set(['USDC', 'FDUSD', 'TUSD', 'DAI', 'BUSD', 'USDP', 'UST', 'USDD', 'PYUSD', 'EUR']);

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
  return cand.slice(0, TOP_N);
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
    const picked = await selectTickers();
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
