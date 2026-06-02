const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = Number(process.env.PORT || 3000);
const API_BASE = process.env.HLSTS_BASE || "http://202.38.77.8/hlsTS";
const AUTH = process.env.HLSTS_AUTH || "";
const JSESSIONID = process.env.HLSTS_JSESSIONID || "";

const cfgPath = path.join(__dirname, "pv-config.json");
if (!fs.existsSync(cfgPath)) {
  fs.writeFileSync(cfgPath, JSON.stringify({
    beam: ["RNG:BEAM:CURR"],
    power: ["SR_PS_BM:current:ai", "SR_PS_QM23:current:ai", "SR_PS_QM24:current:ai", "TL_PS_Q01:current:ai"],
    decay13: [
      "RNG:OPERATION:MODE:bo","RNG:TOPOFF:ALARM:ENABLE","RNG:TOPOFF:DM:Neutron:Err:mbbo","RNG:TOPOFF:DM:Gamma:Err:mbbo",
      "RNG:TOPOFF:IE:Err:mbbo","RNG:TOPOFF:RI:Err:mbbo","RNG:TOPOFF:MPS:Err:mbbo","RNG:TOPOFF:TPS:Err:mbbo",
      "RNG:TOPOFF:BEAM:Err:mbbo","RNG:TOPOFF:KLY:Err:mbbo","RNG:BTemp:alarm:bi","RNG:STemp:alarm:bi","RNG:QTemp:alarm:bi"
    ]
  }, null, 2), "utf8");
}
const pvConfig = JSON.parse(fs.readFileSync(cfgPath, "utf8"));

function toBeijingTimeFromNs(nsStr) {
  const ms = Number(BigInt(String(nsStr)) / 1000000n);
  const d = new Date(ms);
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", hour12: false,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit"
  }).format(d).replace(/\//g, "-");
}

async function fetchPvRange(pv, start, end, agg = "avg") {
  const url = `${API_BASE}/history/nameMap/${encodeURIComponent(pv)}@/${agg}/${encodeURIComponent(start)}/${encodeURIComponent(end)}`;
  const resp = await fetch(url, {
    method: "GET",
    headers: {
      Accept: "application/json, text/plain, */*",
      Authorization: AUTH,
      Cookie: `JSESSIONID=${JSESSIONID}`,
      Referer: "http://202.38.77.8/history/customizedquery"
    }
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status} for PV ${pv}`);
  const data = await resp.json();
  const node = data[pv];
  if (!node || !Array.isArray(node.data)) return [];
  return node.data.map((x) => ({
    pv,
    timestamp_ns: x.timestamp,
    time: toBeijingTimeFromNs(x.timestamp),
    value: x.float_val ?? x.num_val ?? x.str_val ?? null,
    float_val: x.float_val ?? null,
    num_val: x.num_val ?? null,
    str_val: x.str_val ?? null,
    t: x.t ?? null
  }));
}

async function fetchGroup(group, start, end, agg = "avg") {
  const pvs = pvConfig[group];
  if (!pvs) throw new Error(`Unknown group: ${group}`);
  const rows = [];
  for (const pv of pvs) {
    try {
      rows.push(...await fetchPvRange(pv, start, end, agg));
    } catch (e) {
      rows.push({ pv, time: null, value: null, error: e.message });
    }
  }
  return rows;
}

function json(res, code, payload) {
  res.writeHead(code, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(payload));
}

function toCsv(rows) {
  const header = ["pv","time","timestamp_ns","value","float_val","num_val","str_val","t","error"];
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  return [header.join(","), ...rows.map(r => header.map(k => esc(r[k])).join(","))].join("\n");
}

const server = http.createServer(async (req, res) => {
  try {
    const u = new URL(req.url, `http://127.0.0.1:${PORT}`);

    if (req.method === "GET" && u.pathname === "/api/groups") {
      return json(res, 200, { status: "ok", groups: Object.keys(pvConfig) });
    }

    if (req.method === "GET" && u.pathname === "/api/query-range") {
      const group = u.searchParams.get("group");
      const start = u.searchParams.get("start");
      const end = u.searchParams.get("end");
      const agg = u.searchParams.get("agg") || "avg";
      const format = u.searchParams.get("format") || "json";
      if (!group || !start || !end) return json(res, 400, { status: "error", message: "group/start/end 必填" });

      const rows = await fetchGroup(group, start, end, agg);
      if (format === "csv") {
        const csv = toCsv(rows);
        res.writeHead(200, { "Content-Type": "text/csv; charset=utf-8" });
        return res.end(csv);
      }
      return json(res, 200, { status: "ok", group, start, end, agg, count: rows.length, rows });
    }

    return json(res, 404, { status: "error", message: "Not Found" });
  } catch (e) {
    return json(res, 500, { status: "error", message: e.message });
  }
});

server.listen(PORT, () => {
  console.log(`Server running at http://127.0.0.1:${PORT}`);
});
