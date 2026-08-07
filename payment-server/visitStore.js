/**
 * ===================================================================
 * visitStore.js — 사이트 방문자 집계
 * ===================================================================
 * 날짜별로 방문자 수를 기록한다.
 *  - 방문자(UV): 하루 기준 같은 사람은 1명으로 계산 (쿠키 기반 방문자 ID)
 *  - 조회수(PV): 페이지를 열 때마다 1씩 증가
 * 개인정보(IP·이름 등)는 저장하지 않고, 임의로 발급한 방문자 ID만 사용한다.
 * 데이터는 DATA_DIR/visits.json 에 날짜별로 저장한다.
 * ===================================================================
 */
const fs = require("fs");
const path = require("path");

const DATA_DIR = process.env.DATA_DIR || __dirname;
try { fs.mkdirSync(DATA_DIR, { recursive: true }); } catch (e) {}
const DB_PATH = path.join(DATA_DIR, "visits.json");

// { "2026-08-07": { pv: 123, uv: ["vid1","vid2"] }, ... }
function loadAll() {
  try {
    const raw = fs.readFileSync(DB_PATH, "utf-8");
    const data = JSON.parse(raw);
    return data && typeof data === "object" ? data : {};
  } catch (e) {
    return {};
  }
}

let _cache = null;
let _dirty = false;
function db() {
  if (!_cache) _cache = loadAll();
  return _cache;
}
function saveSoon() {
  _dirty = true;
}
// 잦은 디스크 쓰기를 막기 위해 5초마다 한 번만 저장
setInterval(() => {
  if (!_dirty || !_cache) return;
  _dirty = false;
  try { fs.writeFileSync(DB_PATH, JSON.stringify(_cache), "utf-8"); } catch (e) {}
}, 5000).unref?.();

// 한국 시간 기준 날짜 문자열(YYYY-MM-DD)
function dayKey(d = new Date()) {
  const kst = new Date(d.getTime() + 9 * 3600 * 1000);
  return kst.toISOString().slice(0, 10);
}

/** 방문 1건 기록. visitorId 는 쿠키로 유지되는 임의 ID. */
function record(visitorId) {
  const data = db();
  const k = dayKey();
  if (!data[k]) data[k] = { pv: 0, uv: [] };
  data[k].pv += 1;
  if (visitorId && !data[k].uv.includes(visitorId)) data[k].uv.push(visitorId);
  // 오래된 기록 정리(1년 초과)
  const keys = Object.keys(data).sort();
  if (keys.length > 400) delete data[keys[0]];
  saveSoon();
}

function _range(days) {
  const data = db();
  const out = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86400000);
    const k = dayKey(d);
    const rec = data[k] || { pv: 0, uv: [] };
    out.push({ date: k, pv: rec.pv || 0, uv: (rec.uv || []).length, _uv: rec.uv || [] });
  }
  return out;
}

/** 기간 합계. 같은 사람이 여러 날 와도 기간 UV 는 중복 제거해서 계산. */
function summary(days) {
  const rows = _range(days);
  const uvSet = new Set();
  let pv = 0;
  rows.forEach((r) => { pv += r.pv; r._uv.forEach((v) => uvSet.add(v)); });
  return { days, pv, uv: uvSet.size, rows: rows.map(({ date, pv, uv }) => ({ date, pv, uv })) };
}

/** 관리자 화면용: 일간(오늘)·주간(7일)·월간(30일) */
function stats() {
  const today = summary(1);
  const week = summary(7);
  const month = summary(30);
  return {
    today: { pv: today.pv, uv: today.uv, rows: today.rows },
    week: { pv: week.pv, uv: week.uv, rows: week.rows },
    month: { pv: month.pv, uv: month.uv, rows: month.rows },
  };
}

module.exports = { record, stats, summary, dayKey };
