/**
 * ===================================================================
 * reviewStore.js — 고객 후기 저장소
 * ===================================================================
 * 결과지를 받아 본 고객이 남긴 별점·후기를 보관한다.
 *  - 한 주문당 후기 1개 (중복 작성 방지)
 *  - 관리자가 공개/숨김을 정할 수 있고(기본 공개), 삭제도 가능
 *  - 홈 화면에는 공개된 후기만, 이름은 '홍○○' 형태로 가려서 노출
 * 데이터는 DATA_DIR/reviews.json 에 저장한다.
 * ===================================================================
 */
const fs = require("fs");
const path = require("path");
const { nanoid } = require("nanoid");

const DATA_DIR = process.env.DATA_DIR || __dirname;
try { fs.mkdirSync(DATA_DIR, { recursive: true }); } catch (e) {}
const DB_PATH = path.join(DATA_DIR, "reviews.json");

function readAll() {
  try {
    const raw = fs.readFileSync(DB_PATH, "utf-8");
    const data = JSON.parse(raw);
    return data && typeof data === "object" ? data : {};
  } catch (e) {
    return {};
  }
}
function writeAll(data) {
  fs.writeFileSync(DB_PATH, JSON.stringify(data, null, 2), "utf-8");
}

/** 이름 가리기: 홍길동 → 홍○○ */
function maskName(name) {
  const n = String(name || "").trim();
  if (!n) return "익명";
  if (n.length === 1) return n;
  return n[0] + "○".repeat(Math.max(1, n.length - 1));
}

// 후기 사진 저장 폴더
const IMG_DIR = path.join(DATA_DIR, "review_images");
try { fs.mkdirSync(IMG_DIR, { recursive: true }); } catch (e) {}

/** base64 데이터URL을 파일로 저장하고 파일명을 돌려준다. */
function saveImage(dataUrl) {
  const m = String(dataUrl || "").match(/^data:image\/(png|jpe?g|webp);base64,(.+)$/i);
  if (!m) return null;
  const ext = m[1].toLowerCase() === "jpg" ? "jpeg" : m[1].toLowerCase();
  const buf = Buffer.from(m[2], "base64");
  if (buf.length > 3 * 1024 * 1024) return null;   // 3MB 초과 거부
  const name = `${Date.now()}_${nanoid(8)}.${ext === "jpeg" ? "jpg" : ext}`;
  fs.writeFileSync(path.join(IMG_DIR, name), buf);
  return name;
}

/** 저장된 사진 파일의 실제 경로 */
function imagePath(name) {
  const safe = String(name || "").replace(/[^\w.\-]/g, "");
  if (!safe) return null;
  const p = path.join(IMG_DIR, safe);
  return fs.existsSync(p) ? p : null;
}

function deleteImages(names) {
  (names || []).forEach((n) => {
    try {
      const p = imagePath(n);
      if (p) fs.unlinkSync(p);
    } catch (e) {}
  });
}

/** 후기 작성 (주문 1건당 1개) */
function createReview({ userId, orderId, orderName, customerName, rating, content, images }) {
  const all = readAll();
  // 같은 주문에 이미 후기가 있으면 거부
  const dup = Object.values(all).find((r) => r.orderId === orderId);
  if (dup) return { error: "이미 이 주문에 후기를 남기셨습니다." };

  const id = nanoid(12);
  const review = {
    reviewId: id,
    userId: userId || "",
    orderId: orderId || "",
    orderName: orderName || "",
    customerName: customerName || "",
    maskedName: maskName(customerName),
    rating: Math.max(1, Math.min(5, parseInt(rating, 10) || 5)),
    content: String(content || "").slice(0, 1000),
    // 첨부 사진(최대 3장)
    images: (Array.isArray(images) ? images : []).slice(0, 3)
      .map(saveImage).filter(Boolean),
    visible: true,          // 관리자가 숨길 수 있음
    reply: "",              // 사장님 답글
    createdAt: new Date().toISOString(),
  };
  all[id] = review;
  writeAll(all);
  return { review };
}

/** 전체 후기(관리자용, 최신순) */
function listAll() {
  const all = readAll();
  return Object.values(all)
    .sort((a, b) => (String(a.createdAt) < String(b.createdAt) ? 1 : -1));
}

/** 공개 후기만(홈 노출용, 개인정보 제거) */
function listPublic(limit = 30) {
  return listAll()
    .filter((r) => r.visible)
    .slice(0, limit)
    .map((r) => ({
      reviewId: r.reviewId,
      maskedName: r.maskedName || maskName(r.customerName),
      orderName: r.orderName,
      rating: r.rating,
      content: r.content,
      images: r.images || [],
      reply: r.reply || "",
      createdAt: r.createdAt,
    }));
}

/** 평균 별점·개수 요약 */
function summary() {
  const pub = listAll().filter((r) => r.visible);
  if (!pub.length) return { count: 0, avg: 0, dist: { 5: 0, 4: 0, 3: 0, 2: 0, 1: 0 } };
  const dist = { 5: 0, 4: 0, 3: 0, 2: 0, 1: 0 };
  let sum = 0;
  pub.forEach((r) => { sum += r.rating; dist[r.rating] = (dist[r.rating] || 0) + 1; });
  return { count: pub.length, avg: Math.round((sum / pub.length) * 10) / 10, dist };
}

/** 이 주문에 이미 후기가 있는지 */
function hasReviewForOrder(orderId) {
  return listAll().some((r) => r.orderId === orderId);
}

/** 내가 쓴 후기 목록 */
function listByUser(userId) {
  return listAll().filter((r) => r.userId === userId);
}

function updateReview(reviewId, patch) {
  const all = readAll();
  if (!all[reviewId]) return null;
  all[reviewId] = { ...all[reviewId], ...patch };
  writeAll(all);
  return all[reviewId];
}

function deleteReview(reviewId) {
  const all = readAll();
  if (!all[reviewId]) return false;
  deleteImages(all[reviewId].images);   // 첨부 사진도 함께 정리
  delete all[reviewId];
  writeAll(all);
  return true;
}

module.exports = {
  createReview, listAll, listPublic, summary,
  hasReviewForOrder, listByUser, updateReview, deleteReview, maskName,
  imagePath,
};
