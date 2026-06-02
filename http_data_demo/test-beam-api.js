const http = require("http");
const fs = require("fs");
const path = require("path");

const HOST = "202.38.77.8";
const PORT = 80;

// 建议改成你最新 token；也支持环境变量覆盖
const AUTH = process.env.HLSTS_AUTH || "5878a411-2c64-4fb3-ad16-2f8d71f14012";
const JSESSIONID = process.env.HLSTS_JSESSIONID || "5878a411-2c64-4fb3-ad16-2f8d71f14012";

const start = "2026-05-28 10:00:00";
const end = "2026-05-28 15:00:00";

const CHUNK_MAX_MS = (3 * 60 * 60 * 1000) - (2 * 60 * 1000); // 2h58m
const CONCURRENCY = 6;
const RETRY_TIMES = 2;

const BEAM_PVS = ["RNG:BEAM:CURR"];
const DECAY13_PVS = [
  "RNG:OPERATION:MODE:bo",
  "RNG:TOPOFF:ALARM:ENABLE",
  "RNG:TOPOFF:DM:Neutron:Err:mbbo",
  "RNG:TOPOFF:DM:Gamma:Err:mbbo",
  "RNG:TOPOFF:IE:Err:mbbo",
  "RNG:TOPOFF:RI:Err:mbbo",
  "RNG:TOPOFF:MPS:Err:mbbo",
  "RNG:TOPOFF:TPS:Err:mbbo",
  "RNG:TOPOFF:BEAM:Err:mbbo",
  "RNG:TOPOFF:KLY:Err:mbbo",
  "RNG:BTemp:alarm:bi",
  "RNG:STemp:alarm:bi",
  "RNG:QTemp:alarm:bi"
];
const POWER_PREFIXES = ["SR_PS_", "TL_PS_", "LA_PS_"];

function toMs(input) {
  return new Date(input.replace(" ", "T") + "+08:00").getTime();
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

function msToSqlTime(ms) {
  const d = new Date(ms);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).formatToParts(d);
  const get = (k) => parts.find((p) => p.type === k)?.value || "";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}:${get("second")}`;
}

function toBeijingFromTimestamp(ts) {
  const s = String(ts);
  const ms = s.length >= 16 ? Number(BigInt(s) / 1000000n) : Number(s);
  const d = new Date(ms);
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(d).replace(/\//g, "-");
}

function requestJson(pathname) {
  return new Promise((resolve, reject) => {
    const options = {
      host: HOST,
      port: PORT,
      path: pathname,
      method: "GET",
      headers: {
        Accept: "application/json, text/plain, */*",
        Authorization: AUTH,
        Cookie: `JSESSIONID=${JSESSIONID}`,
        Referer: "http://202.38.77.8/history/customizedquery"
      },
      timeout: 20000
    };
    const req = http.request(options, (res) => {
      let raw = "";
      res.on("data", (c) => { raw += c; });
      res.on("end", () => {
        if (res.statusCode !== 200) {
          return reject(new Error(`HTTP ${res.statusCode}: ${raw.slice(0, 200)}`));
        }
        try {
          resolve(JSON.parse(raw));
        } catch (e) {
          reject(new Error(`JSON parse failed: ${e.message}`));
        }
      });
    });
    req.on("timeout", () => { req.destroy(); reject(new Error("request timeout")); });
    req.on("error", (e) => reject(e));
    req.end();
  });
}

async function fetchPvNameList(keyword) {
  const p = `/hlsTS/getPvName/${encodeURIComponent(keyword)}`;
  const arr = await requestJson(p);
  return Array.isArray(arr) ? arr : [];
}

async function discoverPowerPvs() {
  const names = new Set();
  for (const prefix of POWER_PREFIXES) {
    const rows = await fetchPvNameList(prefix);
    for (const item of rows) {
      const name = item?.name;
      if (!name) continue;
      if (
        (name.startsWith("SR_PS_") || name.startsWith("TL_PS_") || name.startsWith("LA_PS_")) &&
        name.endsWith(":current:ai")
      ) names.add(name);
    }
  }
  return Array.from(names).sort();
}

function splitRange(s, e) {
  const out = [];
  const startMs = toMs(s);
  const endMs = toMs(e);
  let cur = startMs;
  while (cur < endMs) {
    const next = Math.min(cur + CHUNK_MAX_MS, endMs);
    out.push({ start: msToSqlTime(cur), end: msToSqlTime(next) });
    cur = next;
  }
  return out;
}

async function fetchPvChunk(pv, s, e) {
  const p = `/hlsTS/history/nameMap/${encodeURIComponent(pv)}@/avg/${encodeURIComponent(s)}/${encodeURIComponent(e)}`;
  const obj = await requestJson(p);
  const node = obj[pv];
  if (!node || !Array.isArray(node.data)) return [];
  return node.data.map((x) => ({
    pv,
    timestamp: String(x.timestamp),
    time: toBeijingFromTimestamp(x.timestamp),
    value: x.float_val ?? x.num_val ?? x.str_val,
    float_val: x.float_val ?? null,
    num_val: x.num_val ?? null,
    str_val: x.str_val ?? null,
    t: x.t ?? null
  }));
}

async function fetchPvWithRetry(pv, s, e) {
  let lastErr = null;
  for (let i = 0; i <= RETRY_TIMES; i++) {
    try {
      return await fetchPvChunk(pv, s, e);
    } catch (e1) {
      lastErr = e1;
      await new Promise((r) => setTimeout(r, 250 * (i + 1)));
    }
  }
  throw lastErr;
}

async function fetchPvWholeRange(pv, s, e) {
  const chunks = splitRange(s, e);
  const all = [];
  for (const c of chunks) {
    const rows = await fetchPvWithRetry(pv, c.start, c.end);
    all.push(...rows);
  }
  const dedup = new Map();
  for (const r of all) dedup.set(`${r.pv}|${r.timestamp}`, r);
  return Array.from(dedup.values()).sort((a, b) => {
    const x = BigInt(a.timestamp);
    const y = BigInt(b.timestamp);
    return x < y ? -1 : x > y ? 1 : 0;
  });
}

async function runWithConcurrency(tasks, limit) {
  const results = new Array(tasks.length);
  let idx = 0;
  async function worker() {
    while (idx < tasks.length) {
      const current = idx++;
      try {
        results[current] = { ok: true, value: await tasks[current]() };
      } catch (e) {
        results[current] = { ok: false, error: e.message };
      }
    }
  }
  const workers = Array.from({ length: Math.min(limit, tasks.length) }, () => worker());
  await Promise.all(workers);
  return results;
}

function saveCsv(filePath, rows) {
  const header = ["pv", "time", "timestamp", "value", "float_val", "num_val", "str_val", "t"];
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = [header.join(",")];
  for (const r of rows) lines.push(header.map((k) => esc(r[k])).join(","));
  fs.writeFileSync(filePath, lines.join("\n"), "utf8");
}

(async () => {
  console.log(`Time range: ${start} ~ ${end}\n`);
  const chunks = splitRange(start, end);
  console.log(`Chunks: ${chunks.length}, max <= 3h each\n`);

  console.log("Discovering all power PVs...");
  const powerPvs = await discoverPowerPvs();
  console.log(`Power PV discovered: ${powerPvs.length}`);

  const allPvs = [...BEAM_PVS, ...powerPvs, ...DECAY13_PVS];
  const uniquePvs = Array.from(new Set(allPvs));
  console.log(`Total PV to query: ${uniquePvs.length}`);
  console.log(`Concurrency: ${CONCURRENCY}, Retry: ${RETRY_TIMES}\n`);

  const tasks = uniquePvs.map((pv) => async () => {
    const rows = await fetchPvWholeRange(pv, start, end);
    return { pv, rows };
  });
  const results = await runWithConcurrency(tasks, CONCURRENCY);

  const flatRows = [];
  let okCount = 0;
  let errCount = 0;
  for (let i = 0; i < results.length; i++) {
    const pv = uniquePvs[i];
    const r = results[i];
    if (!r?.ok) {
      errCount += 1;
      console.log(`\n=== ${pv} | ERROR ===`);
      console.log(r?.error || "unknown error");
      continue;
    }
    okCount += 1;
    const rows = r.value.rows;
    flatRows.push(...rows);
    console.log(`\n=== ${pv} | count=${rows.length} ===`);
    rows.slice(0, 5).forEach((x) => console.log(`${x.time}\t${x.value}\t(${x.timestamp})`));
    if (rows.length > 5) console.log(`... (${rows.length - 5} more)`);
  }

  const out = path.join(__dirname, "api-query-result.csv");
  saveCsv(out, flatRows);
  console.log(`\nDone. ok=${okCount}, error=${errCount}, totalRows=${flatRows.length}`);
  console.log(`CSV saved: ${out}`);
})();
