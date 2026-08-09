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

// 방문자별 마지막 활동 시각(세션 계산용). 30분 넘게 끊기면 '다시 방문'으로 센다.
const SESSION_GAP_MS = 30 * 60 * 1000;
const _lastSeen = new Map();

/**
 * 방문 1건 기록. visitorId 는 쿠키로 유지되는 임의 ID.
 * @param {string} visitorId
 * @param {boolean} newSession true 면 무조건 '새 방문'으로 센다(로그인·로그아웃 직후 등)
 */
function record(visitorId, newSession) {
  const data = db();
  const k = dayKey();
  if (!data[k]) data[k] = { pv: 0, uv: [], visits: 0 };
  if (data[k].visits == null) data[k].visits = 0;   // 과거 기록 호환

  data[k].pv += 1;
  if (visitorId && !data[k].uv.includes(visitorId)) data[k].uv.push(visitorId);

  // ---- 방문 횟수(세션) ----
  // 처음 오거나, 30분 이상 뒤에 다시 오거나, 로그인/로그아웃으로 상태가 바뀌면 '다시 방문'
  const now = Date.now();
  const prev = _lastSeen.get(visitorId);
  if (!prev || newSession || now - prev > SESSION_GAP_MS) {
    data[k].visits += 1;
  }
  if (visitorId) _lastSeen.set(visitorId, now);

  // 오래된 기록 정리(1년 초과)
  const keys = Object.keys(data).sort();
  if (keys.length > 400) delete data[keys[0]];
  saveSoon();
}

/** 로그인/로그아웃 시 호출 — 다음 방문을 '새 방문'으로 잡기 위해 기록을 지운다. */
function resetSession(visitorId) {
  if (visitorId) _lastSeen.delete(visitorId);
}

// ---- 지역(접속 위치) 집계 ----
const _visitorRegion = new Map();   // vid -> 지역명(한 번 확인하면 재사용)
const _regionDone = new Set();      // "날짜|vid" — 하루 한 번만 지역 카운트

/** 방문자의 지역을 이미 알고 있는지 */
function knownRegion(visitorId) { return _visitorRegion.get(visitorId); }

/** 지역 1건 기록(같은 방문자는 하루 1회만 카운트) */
function recordRegion(visitorId, region) {
  if (!region) return;
  _visitorRegion.set(visitorId, region);
  const k = dayKey();
  const doneKey = k + "|" + visitorId;
  if (_regionDone.has(doneKey)) return;
  _regionDone.add(doneKey);
  const data = db();
  if (!data[k]) data[k] = { pv: 0, uv: [], visits: 0 };
  if (!data[k].regions) data[k].regions = {};
  data[k].regions[region] = (data[k].regions[region] || 0) + 1;
  if (_regionDone.size > 20000) _regionDone.clear();  // 메모리 방어
  saveSoon();
}

function _range(days) {
  const data = db();
  const out = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86400000);
    const k = dayKey(d);
    const rec = data[k] || { pv: 0, uv: [], visits: 0 };
    out.push({
      date: k, pv: rec.pv || 0, uv: (rec.uv || []).length,
      visits: rec.visits || 0, _uv: rec.uv || [], regions: rec.regions || {},
    });
  }
  return out;
}

/** 기간 합계. 같은 사람이 여러 날 와도 기간 UV 는 중복 제거해서 계산. */
function summary(days) {
  const rows = _range(days);
  const uvSet = new Set();
  let pv = 0, visits = 0;
  const regions = {};
  rows.forEach((r) => {
    pv += r.pv; visits += r.visits; r._uv.forEach((v) => uvSet.add(v));
    for (const [name, n] of Object.entries(r.regions)) regions[name] = (regions[name] || 0) + n;
  });
  // 많은 순으로 정렬한 배열
  const regionList = Object.entries(regions)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
  return {
    days, pv, visits, uv: uvSet.size, regions: regionList,
    rows: rows.map(({ date, pv, uv, visits }) => ({ date, pv, uv, visits })),
  };
}

/** 관리자 화면용: 일간(오늘)·주간(7일)·월간(30일) */
function stats() {
  const today = summary(1);
  const week = summary(7);
  const month = summary(30);
  return {
    today: { pv: today.pv, uv: today.uv, visits: today.visits, regions: today.regions, rows: today.rows },
    week: { pv: week.pv, uv: week.uv, visits: week.visits, regions: week.regions, rows: week.rows },
    month: { pv: month.pv, uv: month.uv, visits: month.visits, regions: month.regions, rows: month.rows },
  };
}

// ---- IP → 지역명 변환 (무료 ip-api.com 사용, 서버에서만 호출) ----
// 영문/한글 지역명을 짧은 시·도 라벨로 정리한다.
const _REGION_KO = {
  Seoul: "서울", Busan: "부산", Daegu: "대구", Incheon: "인천", Gwangju: "광주",
  Daejeon: "대전", Ulsan: "울산", Sejong: "세종", Gyeonggi: "경기", "Gyeonggi-do": "경기",
  Gangwon: "강원", "Gangwon-do": "강원", Chungbuk: "충북", "North Chungcheong": "충북",
  Chungnam: "충남", "South Chungcheong": "충남", Jeonbuk: "전북", "North Jeolla": "전북",
  Jeonnam: "전남", "South Jeolla": "전남", Gyeongbuk: "경북", "North Gyeongsang": "경북",
  Gyeongnam: "경남", "South Gyeongsang": "경남", Jeju: "제주",
  // 한글 정식 명칭 → 약칭
  "충청남도": "충남", "충청북도": "충북", "전라남도": "전남", "전라북도": "전북",
  "전북특별자치도": "전북", "경상남도": "경남", "경상북도": "경북",
  "강원특별자치도": "강원", "제주특별자치도": "제주",
};
function _shortenKo(regionName) {
  if (!regionName) return null;
  let r = String(regionName).trim();
  if (_REGION_KO[r]) return _REGION_KO[r];
  // 한글 접미사 제거: 서울특별시→서울, 경기도→경기, 제주특별자치도→제주
  r = r.replace(/(특별자치시|특별자치도|특별시|광역시|자치시|자치도)$/, "")
       .replace(/도$/, "");
  return r || regionName;
}

const _pending = new Set();  // 중복 조회 방지
function isPrivateIp(ip) {
  if (!ip) return true;
  ip = ip.replace(/^::ffff:/, "");
  return ip === "127.0.0.1" || ip === "::1" || /^10\./.test(ip) ||
    /^192\.168\./.test(ip) || /^172\.(1[6-9]|2\d|3[01])\./.test(ip);
}

/** IP를 지역명으로 조회해 recordRegion 까지 처리(백그라운드). 페이지 응답은 막지 않는다. */
async function lookupAndRecord(visitorId, ip) {
  if (!visitorId || _visitorRegion.has(visitorId) || _pending.has(visitorId)) return;
  if (isPrivateIp(ip)) { recordRegion(visitorId, "로컬(테스트)"); return; }
  _pending.add(visitorId);
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 4000);
    const r = await fetch(
      `http://ip-api.com/json/${encodeURIComponent(ip)}?fields=status,country,countryCode,regionName&lang=ko`,
      { signal: ctrl.signal }
    );
    clearTimeout(t);
    const d = await r.json();
    if (d && d.status === "success") {
      const region = (d.countryCode === "KR")
        ? (_shortenKo(d.regionName) || "국내")
        : `해외(${d.country || d.countryCode || "기타"})`;
      recordRegion(visitorId, region);
    } else {
      recordRegion(visitorId, "확인 안 됨");
    }
  } catch (e) {
    // 실패해도 서비스에 영향 없음(다음 방문 때 다시 시도)
  } finally {
    _pending.delete(visitorId);
  }
}

module.exports = { record, resetSession, stats, summary, dayKey, knownRegion, recordRegion, lookupAndRecord };
