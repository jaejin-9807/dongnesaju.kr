/**
 * ===================================================================
 * orderStore.js
 * ===================================================================
 * 아주 단순한 주문 저장소. 실서비스에서는 데이터베이스(예: PostgreSQL,
 * MongoDB, 또는 Google Sheets 연동)로 교체하는 것을 권장합니다.
 *
 * 이 프로젝트는 결제 흐름 검증이 목적이므로, 로컬 JSON 파일에
 * 주문 상태를 저장하는 방식을 사용합니다. 서버가 재시작되어도
 * orders.json 파일이 있으면 주문 내역이 유지됩니다.
 * ===================================================================
 */
const fs = require("fs");
const path = require("path");

const DATA_DIR = process.env.DATA_DIR || __dirname;
try { require("fs").mkdirSync(DATA_DIR, { recursive: true }); } catch (e) {}
const DB_PATH = path.join(DATA_DIR, "orders.json");

function readAll() {
  if (!fs.existsSync(DB_PATH)) return {};
  try {
    const raw = fs.readFileSync(DB_PATH, "utf-8");
    return raw ? JSON.parse(raw) : {};
  } catch (e) {
    console.error("주문 데이터 읽기 실패:", e.message);
    return {};
  }
}

function writeAll(data) {
  fs.writeFileSync(DB_PATH, JSON.stringify(data, null, 2), "utf-8");
}

/**
 * 새 주문 생성
 * order = {
 *   orderId, orderName, amount, customerName, customerEmail, customerPhone,
 *   pg: 'toss' | 'kakaopay' | 'naverpay',
 *   status: 'READY' | 'DONE' | 'FAILED' | 'CANCELED',
 *   sajuInfo: { name1, calendarType1, birthYear1, ... } // 사주 주문서 원본 정보
 *   createdAt, updatedAt,
 *   pgMeta: {} // 결제사별 부가 정보(tid, paymentKey 등)
 * }
 */
function createOrder(order) {
  const all = readAll();
  all[order.orderId] = {
    ...order,
    status: order.status || "READY",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
  writeAll(all);
  return all[order.orderId];
}

function getOrder(orderId) {
  const all = readAll();
  return all[orderId] || null;
}

function updateOrder(orderId, patch) {
  const all = readAll();
  if (!all[orderId]) return null;
  all[orderId] = {
    ...all[orderId],
    ...patch,
    updatedAt: new Date().toISOString(),
  };
  writeAll(all);
  return all[orderId];
}

function listOrders() {
  const all = readAll();
  return Object.values(all).sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
}

// 관리자: 주문 이력 삭제
function deleteOrder(orderId) {
  const all = readAll();
  if (!all[orderId]) return false;
  delete all[orderId];
  writeAll(all);
  return true;
}

module.exports = { createOrder, getOrder, updateOrder, listOrders, deleteOrder };
