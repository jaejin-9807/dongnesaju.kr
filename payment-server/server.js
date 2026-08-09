/**
 * ===================================================================
 * server.js - 동네사주카페 통합 서버 (진입점, v4)
 * ===================================================================
 * v4 변경사항: 관리자 페이지에서 실제 결제 없이 샘플 PDF를 바로
 * 생성/다운로드해볼 수 있는 테스트 엔드포인트 추가.
 *   POST /api/admin/sample-pdf  (body: { type: "single" | "couple" })
 * ===================================================================
 */
require("dotenv").config();
const express = require("express");
const path = require("path");
const { nanoid } = require("nanoid");
const cookieMiddleware = require("./cookieMiddleware");

const tossRoutes = require("./routes/toss");
const kakaopayRoutes = require("./routes/kakaopay");
const naverpayRoutes = require("./routes/naverpay");
const authRoutes = require("./routes/auth");
const socialAuthRoutes = require("./routes/socialAuth");
const adminAuthRoutes = require("./routes/adminAuth");
const orderStore = require("./orderStore");
const userStore = require("./userStore");
const visitStore = require("./visitStore");
const { calculateSaju, generatePdf, probeRenderEngines } = require("./sajuEngine");
const { fulfillOrder, PDF_OUTPUT_DIR } = require("./fulfillOrder");
const { sendResultToCustomer, sendResultSmsToCustomer } = require("./mailer");
const kakaoNotify = require("./kakaoNotify");

const { requireCustomer } = authRoutes;
const { requireAdmin } = adminAuthRoutes;

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(cookieMiddleware);

// ---------------------------------------------------------------
// 방문자 집계: 사이트 페이지를 열 때마다 기록한다.
//  - 같은 사람은 하루에 1명으로 계산(방문자 쿠키 vid, 1년 유지)
//  - 관리자 페이지·API·정적 리소스는 집계에서 제외
// ---------------------------------------------------------------
app.use((req, res, next) => {
  try {
    if (req.method !== "GET") return next();
    const p = req.path || "";
    const isPage = p === "/" || p.endsWith(".html");
    const skip = p.startsWith("/api/") || p.startsWith("/admin") || p.includes("admin");
    if (isPage && !skip) {
      let vid = req.cookies && req.cookies.vid;
      if (!vid) {
        vid = nanoid(16);
        res.cookie("vid", vid, { maxAge: 365 * 24 * 3600 * 1000, sameSite: "lax" });
      }
      visitStore.record(vid);
      // 지역(접속 위치)은 방문자당 한 번만, 백그라운드로 조회(페이지 응답을 막지 않음)
      if (!visitStore.knownRegion(vid)) {
        const fwd = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim();
        const ip = fwd || (req.socket && req.socket.remoteAddress) || "";
        visitStore.lookupAndRecord(vid, ip);
      }
    }
  } catch (e) { /* 집계 실패가 서비스에 영향 주지 않도록 무시 */ }
  next();
});

app.use(express.static(path.join(__dirname, "public")));

app.use("/api/auth", authRoutes);
app.use("/api/auth", socialAuthRoutes);
app.use("/api/admin/auth", adminAuthRoutes);

app.use("/api/toss", tossRoutes);
app.use("/api/kakaopay", kakaopayRoutes);
app.use("/api/naverpay", naverpayRoutes);

function resolvePrice(productName) {
  // 프리미엄(전체) 29,800원 / 궁합(2인) 할인가 55,000원 / 이벤트 0원
  // 단품 집중풀이: 나의 사주팔자 9,900원 · 주제별 5,000원
  const PRICES = {
    "이벤트 사주풀이": 0,
    "프리미엄 사주풀이": 29800,
    "궁합사주": 55000,
    "나의 사주팔자": 9900,
    "재물운": 5000,
    "건강운": 5000,
    "부부·가족·인연운": 5000,
    "인간관계·직장운": 5000,
    "명예운": 5000,
  };
  return productName in PRICES ? PRICES[productName] : 29800;
}

const DEFAULT_REPORT_YEAR = Number(process.env.REPORT_YEAR) || 2026;

// 파일명에 쓸 수 없는 문자 제거(섹션 4)
function sanitizeFilename(name) {
  return String(name).replace(/[\\/:*?"<>|\r\n\t]+/g, "").replace(/\s+/g, "_").slice(0, 80) || "리포트";
}

// 주문 정보로부터 표지/기준연도 등 PDF 메타데이터를 구성
function isEventOrder(order) {
  return order.orderName === "이벤트 사주풀이" || Number(order.amount) === 0;
}

// 주문 정보로부터 표지/기준연도 등 PDF 메타데이터를 구성
// 주문번호: 날짜+시간+휴대폰 뒷4자리 조합 (사람이 알아보기 쉽고, 재조회에 편리)
//   예) 20260725-143012-1234
function generateOrderNo(phone) {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const digits = String(phone || "").replace(/\D/g, "");
  const last4 = digits.slice(-4) || "0000";
  const base = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-` +
    `${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}-${last4}`;
  let id = base, i = 1;
  while (orderStore.getOrder(id)) { id = `${base}-${i++}`; }  // 만일의 중복 방지
  return id;
}

function buildPdfMeta(order) {
  const isCouple = order.productType === "couple";
  const isEvent = isEventOrder(order);
  const cal = (order.person1 && order.person1.calendarType) ||
    (order.sajuInfo && order.sajuInfo.calendarType) || "양력";
  return {
    customerName: order.customerName || "의뢰인",
    // 이름 한자 — 결과지 개인화(자원오행·획수 분석)에 사용
    customerNameHanja: order.customerNameHanja || (order.person1 && order.person1.nameHanja) || "",
    reportType: isEvent ? "이벤트 무료 사주" : (isCouple ? "궁합 분석" : (order.orderName || "종합 사주 분석")),
    product: order.orderName || "",   // 상품별 결과지 섹션 선택에 사용
    relationship: order.relationship || "",   // 궁합: 연인/신혼/부부 맞춤 풀이
    reportYear: Number(order.reportYear) || DEFAULT_REPORT_YEAR,
    orderId: order.orderId,
    calendarType: cal,
    birthTimeUnknown: !!(order.person1 && order.person1.birthTimeUnknown),
    teaser: isEvent,   // 이벤트 주문이면 2장짜리 맛보기 PDF 생성
  };
}

function toSajuInfo(person) {
  return {
    name: String(person.name || ""),
    gender: person.gender === "남성" ? "M" : "F",
    calendarType: person.calendarType || "양력",
    isLeapMonth: !!person.isLeapMonth,   // 음력 윤달 여부
    year: Number(person.year),
    month: Number(person.month),
    day: Number(person.day),
    hour: person.hour != null && person.hour !== "" ? Number(person.hour) : 0,
    minute: person.minute != null && person.minute !== "" ? Number(person.minute) : 0,
  };
}

// ===================================================================
// 결과지 자동 생성(1시간 카운트다운) 로직
//  - 고객이 정보를 저장/신청하면 autoGenerateAt = 지금 + AUTO_GEN_MS 로 예약된다.
//  - 백그라운드 스캐너가 1분마다 돌면서, 예약 시각이 지난 주문의 PDF를 자동 생성한다.
//  - 완료되면 resultStatus="READY" 가 되고 마이페이지에서 다운로드가 활성화된다.
// ===================================================================
const AUTO_GEN_MS = (Number(process.env.AUTO_GEN_MINUTES) || 60) * 60 * 1000;

// 주문 하나에 대해 실제 PDF 를 생성하고 주문 레코드를 갱신한다(관리자·자동 공용).
async function generatePdfForOrder(order) {
  if (!order.sajuResult) throw new Error("사주 계산 결과가 없습니다.");
  let sajuResultForPdf = order.sajuResult;
  if (order.productType === "couple" && order.person2 && order.person2.sajuInfo && !order.sajuResult.gunghap) {
    try {
      const enriched = { ...order.sajuInfo, person2: order.person2.sajuInfo };
      sajuResultForPdf = await calculateSaju(enriched);
    } catch (e2) {
      console.error("궁합 재계산 실패(단식 결과로 진행):", e2.message);
    }
  }
  const meta = buildPdfMeta(order);
  const pdfPath = path.join(PDF_OUTPUT_DIR, `${order.orderId}.pdf`);
  const result = await generatePdf(sajuResultForPdf, pdfPath, meta);
  const pdfFilename = (result && result.suggestedFilename) ||
    sanitizeFilename(`${meta.customerName}_${meta.reportType}_${meta.reportYear}`) + ".pdf";
  const updated = orderStore.updateOrder(order.orderId, {
    pdfPath,
    pdfGeneratedAt: new Date().toISOString(),
    pdfEngine: result && result.engine,
    pdfValidation: result && result.validation,
    pdfAiUsed: result && result.aiUsed,
    pdfAiSourceMap: result && result.aiSourceMap,
    pdfFilename,
    resultStatus: "READY",
  });
  return { updated, result };
}

// 결과지 자동 생성 예약을 건다(1시간 카운트다운 시작).
function startAutoGeneration(orderId) {
  return orderStore.updateOrder(orderId, {
    autoGenerateAt: new Date(Date.now() + AUTO_GEN_MS).toISOString(),
    resultStatus: "COUNTDOWN",
  });
}

// 백그라운드 스캐너: 예약 시각이 지난 주문의 PDF 를 순차적으로 자동 생성.
let _scanBusy = false;
async function autoGenScan() {
  if (_scanBusy) return;
  _scanBusy = true;
  try {
    const now = Date.now();
    for (const order of orderStore.listOrders()) {
      if (!order.autoGenerateAt) continue;
      if (order.pdfPath || order.resultStatus === "READY") continue;
      if (order.resultStatus === "GENERATING") continue;
      if (order.status === "CANCELLED") continue;
      if (new Date(order.autoGenerateAt).getTime() > now) continue;
      orderStore.updateOrder(order.orderId, { resultStatus: "GENERATING" });
      try {
        console.log("[자동생성] PDF 생성 시작:", order.orderId);
        await generatePdfForOrder(orderStore.getOrder(order.orderId));
        console.log("[자동생성] PDF 생성 완료:", order.orderId);
      } catch (e) {
        console.error("[자동생성] 실패:", order.orderId, e.message);
        orderStore.updateOrder(order.orderId, { resultStatus: "FAILED", pdfError: e.message });
      }
    }
  } finally {
    _scanBusy = false;
  }
}

app.post("/api/orders/register", requireCustomer, async (req, res) => {
  const {
    productName, productType,
    customerName, customerNameHanja, customerEmail, customerPhone,
    person1, person2, relationship,
  } = req.body;

  if (!productName || !customerName || !person1) {
    return res.status(400).json({ success: false, message: "필수 항목(상품명/이름/생년월일)이 비어 있습니다." });
  }
  // 이메일은 선택. 연락처(휴대폰) 또는 이메일 중 하나는 있어야 결과 안내가 가능하다.
  if (!customerEmail && !customerPhone) {
    return res.status(400).json({ success: false, message: "연락받으실 휴대폰 번호 또는 이메일 중 하나는 입력해 주세요." });
  }
  if (!person1.year || !person1.month || !person1.day) {
    return res.status(400).json({ success: false, message: "생년월일을 정확히 입력해 주세요." });
  }
  if (productType === "couple" && (!person2 || !person2.year || !person2.month || !person2.day)) {
    return res.status(400).json({ success: false, message: "궁합사주는 상대방의 생년월일도 필요합니다." });
  }

  try {
    const sajuInfo1 = toSajuInfo(person1);
    const sajuResult1 = await calculateSaju(sajuInfo1);

    let sajuInfo2 = null;
    let sajuResult2 = null;
    if (productType === "couple") {
      sajuInfo2 = toSajuInfo(person2);
      sajuResult2 = await calculateSaju(sajuInfo2);
    }

    const orderId = generateOrderNo(customerPhone);
    const order = orderStore.createOrder({
      orderId,
      userId: req.currentUser.userId,
      orderName: String(productName),
      amount: resolvePrice(String(productName)),
      pg: null,
      customerName: String(customerName),
      customerNameHanja: customerNameHanja || "",
      customerEmail: String(customerEmail),
      customerPhone: customerPhone || "",
      productType: productType || "single",
      person1: { ...person1, sajuInfo: sajuInfo1 },
      person2: productType === "couple" ? { ...person2, sajuInfo: sajuInfo2 } : null,
      relationship: productType === "couple" ? (relationship || "") : "",
      sajuInfo: sajuInfo1,
      sajuResult: sajuResult1,
      sajuResult2,
      status: "PENDING_PAYMENT",
    });

    // 사장님에게 카카오톡 알림(새 주문 접수) — 설정돼 있을 때만 전송
    kakaoNotify.notify(
      `🧾 [동네사주카페] 새 주문 접수\n` +
      `· 상품: ${order.orderName}\n` +
      `· 의뢰인: ${order.customerName}\n` +
      `· 금액: ${Number(order.amount) === 0 ? "0원(무료 이벤트)" : Number(order.amount).toLocaleString() + "원"}\n` +
      `· 주문번호: ${order.orderId}`
    );

    res.json({ success: true, order });
  } catch (e) {
    console.error("주문 등록/사주 계산 오류:", e.message);
    res.status(500).json({ success: false, message: "사주 계산 중 오류가 발생했습니다: " + e.message });
  }
});

app.get("/api/orders/mine", requireCustomer, (req, res) => {
  const all = orderStore.listOrders();
  const mine = all.filter((o) => o.userId === req.currentUser.userId);
  res.json({ success: true, orders: mine });
});

// 고객 본인: 과거에 받은 결과지(PDF)를 다시 다운로드
app.get("/api/orders/:orderId/pdf", requireCustomer, (req, res) => {
  const order = orderStore.getOrder(req.params.orderId);
  if (!order) return res.status(404).json({ success: false, message: "주문을 찾을 수 없습니다." });
  if (order.userId !== req.currentUser.userId) {
    return res.status(403).json({ success: false, message: "본인 주문의 결과지만 받을 수 있습니다." });
  }
  // 입금(결제) 확인 전에는 열람 불가 — 관리자가 '입금확인'을 눌러야 열린다.
  if (!order.paymentConfirmed) {
    return res.status(403).json({ success: false, message: "입금 확인 후 결과지를 보실 수 있습니다. 계좌이체로 결제하셨다면 채팅상담으로 \"이름 금액 입금\"을 남겨주세요." });
  }
  const fs2 = require("fs");
  if (!order.pdfPath) {
    return res.status(404).json({ success: false, message: "아직 결과지가 준비되지 않았습니다." });
  }
  if (!fs2.existsSync(order.pdfPath)) {
    // 경로는 있는데 파일이 없는 경우(예: 저장공간 초기화). 관리자가 다시 생성하면 복구됨.
    return res.status(404).json({ success: false, message: "결과지 파일을 다시 준비 중입니다. 잠시 후 다시 시도하거나 사장님께 문의해 주세요." });
  }
  // '사주결과 보기'는 여러 번 볼 수 있게 한다(다운로드/뷰어 앱 없이 브라우저에서 바로 열람).
  // 관리자 참고용으로 최초 확인 시각만 기록한다.
  const patch = { lastViewedAt: new Date().toISOString() };
  if (!order.viewedAt) patch.viewedAt = new Date().toISOString();
  if (!order.downloadedAt) patch.downloadedAt = new Date().toISOString();
  orderStore.updateOrder(order.orderId, patch);
  const meta = buildPdfMeta(order);
  const filename = order.pdfFilename ||
    (sanitizeFilename(`${meta.customerName}_${meta.reportType}_${meta.reportYear}`) + ".pdf");
  // 기본은 브라우저에서 바로 보기(inline). ?dl=1 이면 파일로 저장(attachment).
  const disp = req.query.dl ? "attachment" : "inline";
  res.setHeader("Content-Disposition", `${disp}; filename*=UTF-8''${encodeURIComponent(filename)}`);
  res.setHeader("Content-Type", "application/pdf");
  res.sendFile(order.pdfPath, (err) => { if (err && !res.headersSent) res.status(500).json({ success: false, message: "파일 전송 실패: " + err.message }); });
});

// ---------------------------------------------------------------
// 결제대기 상태 주문 취소 (본인 주문만 가능)
// 상품을 잘못 고르거나 생년월일을 잘못 입력한 경우, 이 주문을 취소하고
// 홈페이지에서 새로 주문서를 작성하도록 안내한다.
// ---------------------------------------------------------------
app.post("/api/orders/:orderId/cancel", requireCustomer, (req, res) => {
  const order = orderStore.getOrder(req.params.orderId);
  if (!order) return res.status(404).json({ success: false, message: "주문을 찾을 수 없습니다." });
  if (order.userId !== req.currentUser.userId) {
    return res.status(403).json({ success: false, message: "본인 주문만 취소할 수 있습니다." });
  }
  if (order.status !== "PENDING_PAYMENT") {
    return res.status(400).json({ success: false, message: "결제대기 상태의 주문만 취소할 수 있습니다." });
  }
  const updated = orderStore.updateOrder(order.orderId, { status: "CANCELLED" });
  res.json({ success: true, order: updated });
});

// ---------------------------------------------------------------
// 이벤트(0원) 무료 사주 신청: PG 결제 없이 바로 접수하고 사장님 확인 대기 상태로 전환.
// 사장님은 관리자 페이지에서 '운세풀이 시작하기'로 2장짜리 맛보기 PDF를 생성해 전달한다.
// ---------------------------------------------------------------
app.post("/api/orders/:orderId/free-claim", requireCustomer, async (req, res) => {
  const order = orderStore.getOrder(req.params.orderId);
  if (!order) return res.status(404).json({ success: false, message: "주문을 찾을 수 없습니다." });
  if (order.userId !== req.currentUser.userId) {
    return res.status(403).json({ success: false, message: "본인 주문만 신청할 수 있습니다." });
  }
  if (Number(order.amount) !== 0) {
    return res.status(400).json({ success: false, message: "이벤트(0원) 주문만 무료로 신청할 수 있습니다." });
  }
  if (order.status !== "PENDING_PAYMENT") {
    return res.status(400).json({ success: false, message: "이미 접수된 주문입니다." });
  }
  try {
    await app.locals.fulfillOrder(order.orderId);
    // 정보 저장(무료 신청) 즉시 1시간 카운트다운을 시작한다.
    const updated = startAutoGeneration(order.orderId);
    res.json({ success: true, order: updated });
  } catch (e) {
    console.error("이벤트 무료 신청 처리 오류:", e.message);
    res.status(500).json({ success: false, message: "무료 신청 처리 중 오류가 발생했습니다: " + e.message });
  }
});

app.post("/api/orders/:orderId/select-pg", (req, res) => {
  const { pg, customerPhone } = req.body;
  const order = orderStore.getOrder(req.params.orderId);
  if (!order) return res.status(404).json({ success: false, message: "주문을 찾을 수 없습니다." });

  const updated = orderStore.updateOrder(order.orderId, {
    pg,
    customerPhone: customerPhone || order.customerPhone,
  });
  res.json({ success: true, order: updated });
});

app.get("/api/orders/:orderId", (req, res) => {
  const order = orderStore.getOrder(req.params.orderId);
  if (!order) return res.status(404).json({ success: false, message: "주문을 찾을 수 없습니다." });
  res.json({ success: true, order });
});

// ---------------------------------------------------------------
// 관리자(사장님) 전용: 전체 주문 목록 + PDF 생성
// ---------------------------------------------------------------
app.get("/api/admin/orders", requireAdmin, (req, res) => {
  res.json({ success: true, orders: orderStore.listOrders() });
});

// 관리자: 회원(가입자) 명단 + 각 회원의 주문 수
app.get("/api/admin/users", requireAdmin, (req, res) => {
  const orders = orderStore.listOrders();
  const countByUser = {};
  for (const o of orders) { if (o.userId) countByUser[o.userId] = (countByUser[o.userId] || 0) + 1; }
  const users = userStore.listUsers().map((u) => ({ ...u, orderCount: countByUser[u.userId] || 0 }));
  res.json({ success: true, users });
});

app.post("/api/admin/orders/:orderId/generate-pdf", requireAdmin, async (req, res) => {
  const order = orderStore.getOrder(req.params.orderId);
  if (!order) return res.status(404).json({ success: false, message: "주문을 찾을 수 없습니다." });
  if (!order.sajuResult) return res.status(400).json({ success: false, message: "사주 계산 결과가 없습니다." });

  try {
    const { updated, result } = await generatePdfForOrder(order);
    res.json({ success: true, order: updated, render: result });
  } catch (e) {
    console.error("관리자 PDF 생성 오류:", e.message);
    res.status(500).json({ success: false, message: "PDF 생성 중 오류가 발생했습니다: " + e.message });
  }
});

// 관리자: 결과지 재다운로드 1회 허용(고객이 다시 받을 수 있게 활성화)
app.post("/api/admin/orders/:orderId/reenable-download", requireAdmin, (req, res) => {
  const order = orderStore.getOrder(req.params.orderId);
  if (!order) return res.status(404).json({ success: false, message: "주문을 찾을 수 없습니다." });
  const updated = orderStore.updateOrder(order.orderId, { redownloadAllowed: true });
  res.json({ success: true, order: updated });
});

// 관리자: 주문 이력 삭제
app.delete("/api/admin/orders/:orderId", requireAdmin, (req, res) => {
  const order = orderStore.getOrder(req.params.orderId);
  if (!order) return res.status(404).json({ success: false, message: "주문을 찾을 수 없습니다." });
  const fs2 = require("fs");
  try { if (order.pdfPath && fs2.existsSync(order.pdfPath)) fs2.unlinkSync(order.pdfPath); } catch (e) {}
  const ok = orderStore.deleteOrder(order.orderId);
  res.json({ success: ok });
});

// 관리자: (계좌이체 등) 입금 확인 → 결제완료 처리
// ★ 결과지는 자동 생성하지 않는다. 관리자가 '운세풀이'를 눌러야만 생성되고,
//    그때부터 고객 마이페이지의 다운로드 버튼이 활성화된다.
app.post("/api/admin/orders/:orderId/confirm-payment", requireAdmin, (req, res) => {
  const order = orderStore.getOrder(req.params.orderId);
  if (!order) return res.status(404).json({ success: false, message: "주문을 찾을 수 없습니다." });
  const updated = orderStore.updateOrder(order.orderId, {
    status: "PAID_WAITING_DELIVERY",
    paidAt: new Date().toISOString(),
    paidConfirmedBy: "admin",
    paymentConfirmed: true,                 // 이 순간부터 고객이 결과지 열람 가능
    paymentConfirmedAt: new Date().toISOString(),
  });
  res.json({ success: true, order: updated });
});

app.get("/api/admin/orders/:orderId/pdf", requireAdmin, (req, res) => {
  const order = orderStore.getOrder(req.params.orderId);
  if (!order || !order.pdfPath) {
    return res.status(404).json({ success: false, message: "결과지가 아직 준비되지 않았습니다." });
  }
  const fs2 = require("fs");
  if (!fs2.existsSync(order.pdfPath)) {
    return res.status(404).json({ success: false, message: "결과지 파일이 없습니다. '운세풀이 즉시생성'으로 다시 만들어 주세요. (예전 파일이 저장공간 초기화로 삭제된 경우입니다)" });
  }
  const meta = buildPdfMeta(order);
  const filename = order.pdfFilename ||
    (sanitizeFilename(`${meta.customerName}_${meta.reportType}_${meta.reportYear}`) + ".pdf");
  res.setHeader("Content-Disposition", `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`);
  res.setHeader("Content-Type", "application/pdf");
  res.sendFile(order.pdfPath, (err) => { if (err && !res.headersSent) res.status(500).json({ success: false, message: "파일 전송 실패: " + err.message }); });
});

// ---------------------------------------------------------------
// 관리자 전용: 완성된 PDF를 고객 이메일로 원클릭 발송
// (관리자가 메일 주소를 따로 입력할 필요 없이, 주문에 저장된 customerEmail로 자동 발송)
// ---------------------------------------------------------------
app.post("/api/admin/orders/:orderId/send-email", requireAdmin, async (req, res) => {
  const order = orderStore.getOrder(req.params.orderId);
  if (!order) return res.status(404).json({ success: false, message: "주문을 찾을 수 없습니다." });
  if (!order.pdfPath) {
    return res.status(400).json({ success: false, message: "먼저 운세풀이(PDF 생성)를 완료해 주세요." });
  }

  try {
    await sendResultToCustomer(order, order.pdfPath);
    const updated = orderStore.updateOrder(order.orderId, {
      status: "DELIVERED",
      deliveredAt: new Date().toISOString(),
      deliveredVia: "email",
    });
    res.json({ success: true, order: updated });
  } catch (e) {
    console.error("고객 메일 발송 오류:", e.message);
    let hint = e.message;
    if (/ETIMEDOUT|timeout|ECONNECTION|ECONNREFUSED|ENOTFOUND/i.test(e.message)) {
      hint = "메일 서버에 접속하지 못했습니다. Railway 환경변수(MAIL_HOST/MAIL_USER/MAIL_PASS)와 네이버 'POP3/SMTP 사용함' 설정을 확인해 주세요.";
    } else if (/auth|invalid login|535|자격/i.test(e.message)) {
      hint = "메일 로그인에 실패했습니다. MAIL_USER(전체 이메일 주소)와 MAIL_PASS(네이버 비밀번호/앱 비밀번호)를 확인해 주세요.";
    } else if (/설정/.test(e.message)) {
      hint = "메일 발송 설정(MAIL_HOST/MAIL_USER/MAIL_PASS)이 아직 등록되지 않았습니다. Railway 환경변수에 추가해 주세요.";
    }
    res.status(500).json({ success: false, message: hint });
  }
});

// ---------------------------------------------------------------
// 관리자 전용: 완성된 PDF 준비 안내를 고객 휴대폰으로 원클릭 문자 발송
// ★ 아직 실제 SMS 발송사 연동 전이라 지금은 로그만 남기는 스텁입니다.
//   (.env에 SMS 발송사 API 키를 채운 뒤 mailer.js의 sendResultSmsToCustomer를 구현하면
//    이 엔드포인트는 코드 수정 없이 바로 실제 문자를 발송하게 됩니다.)
// ---------------------------------------------------------------
app.post("/api/admin/orders/:orderId/send-sms", requireAdmin, async (req, res) => {
  const order = orderStore.getOrder(req.params.orderId);
  if (!order) return res.status(404).json({ success: false, message: "주문을 찾을 수 없습니다." });
  if (!order.pdfPath) {
    return res.status(400).json({ success: false, message: "먼저 운세풀이(PDF 생성)를 완료해 주세요." });
  }

  try {
    await sendResultSmsToCustomer(order, `${process.env.BASE_URL || ""}/api/admin/orders/${order.orderId}/pdf`);
    res.json({
      success: true,
      simulated: true,
      message: "문자 발송 기능은 아직 준비 중입니다. (관리자 설정에서 SMS 연동 키를 등록하면 바로 사용할 수 있어요)",
    });
  } catch (e) {
    console.error("고객 문자 발송 오류:", e.message);
    res.status(500).json({ success: false, message: "문자 발송 중 오류가 발생했습니다: " + e.message });
  }
});

// ---------------------------------------------------------------
// 관리자 전용: 사이트 방문자 통계 (일간·주간·월간)
// ---------------------------------------------------------------
app.get("/api/admin/visits", requireAdmin, (req, res) => {
  try {
    res.json({ success: true, stats: visitStore.stats() });
  } catch (e) {
    res.status(500).json({ success: false, message: "방문자 통계를 불러오지 못했습니다: " + e.message });
  }
});

// ---------------------------------------------------------------
// 관리자 전용: 음성인식(OpenAI) · 해석AI(Anthropic) 키 상태 진단
//  "정밀 인식이 안 된다"고 할 때 원인을 바로 알려준다.
// ---------------------------------------------------------------
app.get("/api/admin/voice-test", requireAdmin, async (req, res) => {
  const out = { openai: {}, anthropic: {} };

  // 1) OpenAI (Whisper)
  const okey = (process.env.OPENAI_API_KEY || "").trim();
  if (!okey) {
    out.openai = { ok: false, status: "없음",
      detail: "Railway Variables에 OPENAI_API_KEY가 없습니다. 이름 철자를 확인해 주세요." };
  } else if (!okey.startsWith("sk-")) {
    out.openai = { ok: false, status: "형식오류",
      detail: "키가 'sk-'로 시작하지 않습니다. 값을 다시 복사해 넣어 주세요." };
  } else {
    // ★ 인증만 보는 /v1/models 로는 '잔액 0원'을 걸러내지 못한다.
    //   실제 Whisper 에 0.2초 무음 파일을 보내, 결제까지 되는지(=사용 가능한지) 확인한다.
    try {
      const wav = (() => {
        const rate = 8000, n = Math.floor(0.2 * rate), dataLen = n * 2;
        const b = Buffer.alloc(44 + dataLen);
        b.write("RIFF", 0); b.writeUInt32LE(36 + dataLen, 4); b.write("WAVE", 8);
        b.write("fmt ", 12); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20);
        b.writeUInt16LE(1, 22); b.writeUInt32LE(rate, 24); b.writeUInt32LE(rate * 2, 28);
        b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34);
        b.write("data", 36); b.writeUInt32LE(dataLen, 40);
        return b;
      })();
      const form = new FormData();
      form.append("file", new Blob([wav], { type: "audio/wav" }), "test.wav");
      form.append("model", process.env.OPENAI_STT_MODEL || "whisper-1");
      form.append("language", "ko");
      const r = await fetch("https://api.openai.com/v1/audio/transcriptions", {
        method: "POST", headers: { Authorization: `Bearer ${okey}` }, body: form,
      });
      const bodyTxt = await r.text().catch(() => "");
      if (r.ok) {
        out.openai = { ok: true, status: "정상 (잔액 있음)",
          detail: "실제 음성 변환까지 성공했습니다. 녹음 기능을 바로 사용할 수 있습니다." };
      } else if (r.status === 401) {
        out.openai = { ok: false, status: "인증실패(401)",
          detail: "키가 잘못되었거나 폐기되었습니다. OpenAI에서 새 키를 발급해 교체해 주세요." };
      } else if (r.status === 429) {
        const noCredit = /insufficient_quota|exceeded your current quota|billing/i.test(bodyTxt);
        out.openai = { ok: false, status: noCredit ? "잔액부족 — 충전 필요" : "요청한도 초과(429)",
          detail: noCredit
            ? "키는 정상이지만 <b>크레딧이 없습니다</b>. platform.openai.com → Billing 에서 결제수단 등록 후 최소 $5를 충전해 주세요. (ChatGPT 구독과 API 요금은 별개입니다)"
            : "짧은 시간에 요청이 많았습니다. 잠시 후 다시 확인해 주세요." };
      } else if (r.status === 400 && /model/i.test(bodyTxt)) {
        out.openai = { ok: false, status: "모델 오류(400)",
          detail: "OPENAI_STT_MODEL 값을 확인해 주세요. 기본값은 whisper-1 입니다." };
      } else {
        out.openai = { ok: false, status: `오류(${r.status})`, detail: bodyTxt.slice(0, 200) };
      }
    } catch (e) {
      out.openai = { ok: false, status: "연결실패", detail: e.message };
    }
  }

  // 2) Anthropic (결과지 해석 + 음성 필드추출)
  const akey = (process.env.ANTHROPIC_API_KEY || "").trim();
  if (!akey) {
    out.anthropic = { ok: false, status: "없음", detail: "ANTHROPIC_API_KEY가 없습니다." };
  } else {
    try {
      const r = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "content-type": "application/json", "x-api-key": akey, "anthropic-version": "2023-06-01" },
        body: JSON.stringify({
          model: process.env.ANTHROPIC_MODEL || "claude-sonnet-4-5",
          max_tokens: 8,
          messages: [{ role: "user", content: "ok" }],
        }),
      });
      // 실제 메시지 생성(과금 경로)까지 호출하므로 잔액 부족도 여기서 드러난다.
      const t = await r.text().catch(() => "");
      if (r.ok) {
        out.anthropic = { ok: true, status: "정상 (잔액 있음)",
          detail: "실제 해석 호출까지 성공했습니다. 결과지 AI 해석이 정상 작동합니다." };
      } else if (r.status === 401) {
        out.anthropic = { ok: false, status: "인증실패(401)",
          detail: "키가 잘못되었거나 폐기되었습니다. console.anthropic.com 에서 새 키를 발급해 교체해 주세요." };
      } else if (r.status === 400 && /credit balance is too low|billing/i.test(t)) {
        out.anthropic = { ok: false, status: "잔액부족 — 충전 필요",
          detail: "키는 정상이지만 <b>크레딧이 없습니다</b>. console.anthropic.com → Billing 에서 충전해 주세요. 이 상태면 결과지 해석이 고정 문구로 대체되어 <b>내용이 서로 비슷해집니다</b>." };
      } else if (r.status === 429) {
        out.anthropic = { ok: false, status: "요청한도 초과(429)",
          detail: "잠시 후 다시 확인해 주세요. 반복되면 Billing의 사용 한도(Usage limits)를 확인하세요." };
      } else if (r.status === 404 && /model/i.test(t)) {
        out.anthropic = { ok: false, status: "모델 오류(404)",
          detail: `ANTHROPIC_MODEL 값(${process.env.ANTHROPIC_MODEL || "claude-sonnet-4-5"})을 확인해 주세요.` };
      } else {
        out.anthropic = { ok: false, status: `오류(${r.status})`, detail: t.slice(0, 200) };
      }
    } catch (e) {
      out.anthropic = { ok: false, status: "연결실패", detail: e.message };
    }
  }

  res.json({ success: true, result: out });
});

// ---------------------------------------------------------------
// 음성 녹음 → 텍스트 변환 (OpenAI Whisper)
//  브라우저 내장 음성인식보다 정확도가 훨씬 높아, 장년층 발화·한자 훈음도 잘 잡는다.
//  .env(OPENAI_API_KEY)가 없으면 실패를 돌려주고, 클라이언트는 기존 방식으로 폴백한다.
// ---------------------------------------------------------------
app.post(
  "/api/voice/transcribe",
  requireCustomer,
  express.raw({ type: ["audio/*", "application/octet-stream"], limit: "25mb" }),
  async (req, res) => {
    const key = process.env.OPENAI_API_KEY;
    if (!key) {
      return res.json({ success: false, message: "whisper_not_configured" });
    }
    const buf = req.body;
    if (!buf || !buf.length) {
      return res.status(400).json({ success: false, message: "녹음 파일이 비어 있습니다." });
    }
    try {
      const ct = String(req.headers["content-type"] || "audio/webm");
      const ext = ct.includes("mp4") ? "mp4" : ct.includes("ogg") ? "ogg" : ct.includes("wav") ? "wav" : "webm";
      const form = new FormData();
      form.append("file", new Blob([buf], { type: ct }), `voice.${ext}`);
      form.append("model", process.env.OPENAI_STT_MODEL || "whisper-1");
      form.append("language", "ko");
      // 인식 정확도를 높이는 힌트(도메인 어휘)
      form.append(
        "prompt",
        "사주 정보 받아쓰기. 이름, 성별(남자/여자), 혼인 여부(기혼/미혼), 양력/음력/윤달, " +
        "생년월일, 태어난 시각(오전/오후/새벽/저녁), 휴대폰 번호, 이메일. " +
        "한자 이름은 '클 홍, 길할 길, 아이 동'처럼 뜻과 음으로 말합니다."
      );
      const r = await fetch("https://api.openai.com/v1/audio/transcriptions", {
        method: "POST",
        headers: { Authorization: `Bearer ${key}` },
        body: form,
      });
      if (!r.ok) {
        const errTxt = await r.text().catch(() => "");
        console.error("Whisper 오류:", r.status, errTxt.slice(0, 200));
        return res.json({ success: false, message: "whisper_failed", code: r.status });
      }
      const data = await r.json();
      const text = (data && data.text ? String(data.text) : "").trim();
      if (!text) return res.json({ success: false, message: "empty_transcript" });
      res.json({ success: true, transcript: text });
    } catch (e) {
      console.error("음성 변환 실패:", e.message);
      res.json({ success: false, message: "whisper_error", code: e.message });
    }
  }
);

// ---------------------------------------------------------------
// 음성 입력 → 필드 자동 추출 (Claude). 장년층 편의: 말로 이름·생년월일·시각을 채운다.
//  "어…음…그러니까" 같은 추임새·숨소리는 무시하고 사주 정보만 뽑아낸다.
// ---------------------------------------------------------------
async function parseVoiceWithClaude(transcript) {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) throw new Error("NO_KEY");
  const model = process.env.ANTHROPIC_MODEL || "claude-sonnet-4-5";
  const system =
    "너는 한국어 음성 인식 결과에서 사람의 사주 정보를 추출하는 도우미다. " +
    "'어, 음, 그러니까, 뭐더라, 아이고' 같은 감탄사·추임새·숨소리·군더더기는 모두 무시하고, 오직 요청한 JSON만 출력한다. 설명이나 인사말은 절대 붙이지 않는다.";
  const user =
    "다음 음성 텍스트에서 이름/이름한자/성별/혼인여부/양력음력/생년/월/일/태어난시(0~23)/분을 뽑아 JSON으로만 답해줘.\n" +
    "- 모르는 값은 null. 이름(name)은 조사(이,가,은,는)를 떼고 순수 한글 이름만.\n" +
    "- 이름 한자: 화자가 훈음(뜻+음) 방식으로 한자를 불러줄 수 있다. 예: '클 홍, 길할 길, 아이 동' → 洪(클 홍)·吉(길할 길)·童(아이 동). '나무 목', '빛날 현', '어질 인'처럼 '<뜻> <음>' 형태를 각 글자의 한자로 변환하라.\n" +
    "  음성 인식이 부정확해 '길할길짜/아이 동짜'처럼 들려도 훈음의 의도(예: 길할 길=吉, 아이 동=童)를 최대한 유추하라.\n" +
    "  hanjaChars는 name의 각 글자 순서에 맞춘 한자 배열(해당 글자의 한자를 모르면 그 자리는 빈 문자열 \"\"). 화자가 한자를 아예 말하지 않았으면 hanjaChars는 null.\n" +
    "  예: name='홍길동', 화자가 '클 홍 길할 길 아이 동' → hanjaChars=['洪','吉','童'].\n" +
    "- 시각(hour)은 24시간제로: '오후 2시'·'낮 2시'→14, '오후 3시'·'낮 3시'→15, '저녁 7시'→19, '오전 9시'→9, '밤 11시'→23, '자정'→0, '정오'→12. '세 시'처럼 한글 숫자도 인식(세=3). '반'은 30분.\n" +
    "- 연도가 두 자리면 상식적으로 보정(31~99→19xx, 00~30→20xx).\n" +
    "- calendarType은 '양력'|'음력'|'음력윤달'|null. '윤달'이라 하면 '음력윤달'.\n" +
    "- gender는 '남성'|'여성'|null.\n" +
    "- marital은 '기혼'|'미혼'|null. '결혼했다/결혼했고/유부남/유부녀/남편/아내/애 있다'→기혼, '솔로/싱글/혼자/미혼/결혼 안 했다'→미혼.\n" +
    "- phone(휴대폰 번호): 한국어로 부른 숫자를 아라비아 숫자로 바꿔라. 공/영/빵=0, 일=1, 이=2, 삼=3, 사=4, 오=5, 육/륙=6, 칠=7, 팔=8, 구=9. " +
    "예: '공일공 일이삼사 일이삼사'→'01012341234'. 숫자만 10~11자리 문자열로. 없으면 null.\n" +
    "- email(이메일): 화자가 아이디와 도메인을 말한다. '골뱅이/앳'→@, '닷/점/쩜'→., 도메인은 '네이버닷컴'→naver.com, '지메일/구글'→gmail.com, '다음'→daum.net, '한메일'→hanmail.net, '네이트'→nate.com, '핫메일'→hotmail.com, '야후'→yahoo.com. " +
    "영어 철자를 한 글자씩 말하면(에이,비,씨…) 알파벳으로 합쳐라. 예: '길동 골뱅이 네이버 닷컴'→'gildong@naver.com'(아이디를 한글로만 말하면 그대로 두되 영문 스펠링이 있으면 그것을 우선). 없으면 null.\n" +
    '출력 형식(JSON only): {"name":string|null,"hanjaChars":array|null,"gender":string|null,"marital":string|null,"phone":string|null,"email":string|null,"calendarType":string|null,"year":number|null,"month":number|null,"day":number|null,"hour":number|null,"minute":number|null}\n\n' +
    '음성 텍스트: "' + String(transcript).slice(0, 1200) + '"';
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01" },
    body: JSON.stringify({ model, max_tokens: 400, system, messages: [{ role: "user", content: user }] }),
  });
  if (!r.ok) throw new Error("CLAUDE_" + r.status);
  const data = await r.json();
  const text = (data.content && data.content[0] && data.content[0].text) || "";
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("NO_JSON");
  const f = JSON.parse(m[0]);
  // 값 정규화(범위 밖 방어)
  const clampInt = (v, lo, hi) => (v == null ? null : Math.max(lo, Math.min(hi, parseInt(v, 10))) || (v === 0 ? 0 : null));
  const fmtPhone = (v) => {
    if (!v) return null;
    let d = String(v).replace(/\D/g, "");
    if (d.length > 11) d = d.slice(0, 11);
    if (d.length === 11) return d.replace(/(\d{3})(\d{4})(\d{4})/, "$1-$2-$3");
    if (d.length === 10) return d.replace(/(\d{3})(\d{3})(\d{4})/, "$1-$2-$3");
    return d.length >= 9 ? d : null;
  };
  return {
    name: f.name || null,
    hanjaChars: Array.isArray(f.hanjaChars) ? f.hanjaChars.map((x) => (x == null ? "" : String(x))) : null,
    gender: (f.gender === "남성" || f.gender === "여성") ? f.gender : null,
    marital: (f.marital === "기혼" || f.marital === "미혼") ? f.marital : null,
    phone: fmtPhone(f.phone),
    email: (f.email && /\S+@\S+\.\S+/.test(String(f.email))) ? String(f.email).replace(/\s+/g, "").toLowerCase() : null,
    calendarType: ["양력", "음력", "음력윤달"].includes(f.calendarType) ? f.calendarType : null,
    year: f.year ? parseInt(f.year, 10) : null,
    month: clampInt(f.month, 1, 12),
    day: clampInt(f.day, 1, 31),
    hour: (f.hour == null ? null : clampInt(f.hour, 0, 23)),
    minute: (f.minute == null ? null : clampInt(f.minute, 0, 59)),
  };
}

app.post("/api/voice/parse", requireCustomer, async (req, res) => {
  const transcript = ((req.body && req.body.transcript) || "").toString().trim();
  if (!transcript) return res.status(400).json({ success: false, message: "인식된 음성이 없습니다." });
  try {
    const fields = await parseVoiceWithClaude(transcript);
    res.json({ success: true, fields });
  } catch (e) {
    // 실패(키 없음/모델 오류 등) → 클라이언트가 로컬 정규식 파서로 대체한다.
    console.error("음성 파싱 실패:", e.message);
    res.json({ success: false, message: "voice_parse_failed", code: e.message });
  }
});

// ---------------------------------------------------------------
// 관리자 전용: 실제 결제/회원 데이터를 건드리지 않고, 임의의 테스트 인물로
// 사주 계산 + PDF 생성을 즉시 미리 볼 수 있는 샘플 엔드포인트.
// 배포 전 "운세풀이 시작하기"를 눌렀을 때 어떤 PDF가 나오는지 검증하는 용도.
// ---------------------------------------------------------------
const SAMPLE_PEOPLE = {
  single: { name: "홍길동(샘플)", gender: "M", calendarType: "양력", year: 1990, month: 5, day: 15, hour: 10, minute: 30 },
  couple: [
    { name: "홍길동(샘플)", gender: "M", calendarType: "양력", year: 1990, month: 5, day: 15, hour: 10, minute: 30 },
    { name: "김영희(샘플)", gender: "F", calendarType: "양력", year: 1992, month: 9, day: 3, hour: 22, minute: 0 },
  ],
};

app.post("/api/admin/sample-pdf", requireAdmin, async (req, res) => {
  const type = req.body.type === "couple" ? "couple" : "single";

  try {
    let sajuResult;
    if (type === "single") {
      sajuResult = await calculateSaju(SAMPLE_PEOPLE.single);
    } else {
      // 궁합사주 샘플은 첫 번째 인물 기준으로 결과지를 생성한다(결과지 양식 확인용).
      sajuResult = await calculateSaju(SAMPLE_PEOPLE.couple[0]);
    }

    const sampleId = "sample_" + nanoid(8);
    const pdfPath = path.join(PDF_OUTPUT_DIR, `${sampleId}.pdf`);
    const sampleMeta = {
      customerName: type === "couple" ? SAMPLE_PEOPLE.couple[0].name : SAMPLE_PEOPLE.single.name,
      reportType: type === "couple" ? "궁합 분석" : "종합 사주 분석",
      reportYear: DEFAULT_REPORT_YEAR,
      orderId: sampleId,
      calendarType: "양력",
    };
    await generatePdf(sajuResult, pdfPath, sampleMeta);

    const filename = `샘플_사주풀이_결과지_${type}.pdf`;
    res.setHeader("Content-Disposition", `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`);
    res.setHeader("Content-Type", "application/pdf");
    res.sendFile(pdfPath);
  } catch (e) {
    console.error("샘플 PDF 생성 오류:", e.message);
    res.status(500).json({ success: false, message: "샘플 PDF 생성 중 오류가 발생했습니다: " + e.message });
  }
});

// ---------------------------------------------------------------
// 관리자 전용: PDF 렌더 엔진 헬스체크 (Playwright/WeasyPrint/LibreOffice 가용성)
// ---------------------------------------------------------------
app.get("/api/admin/render-health", requireAdmin, async (req, res) => {
  try {
    const status = await probeRenderEngines();
    res.json({ success: true, status });
  } catch (e) {
    res.status(500).json({ success: false, message: e.message });
  }
});

// ---------------------------------------------------------------
// 카카오톡 "나에게 보내기" 알림 연결 (사장님 1회 인증)
//   1) 관리자 로그인 상태에서 /api/admin/kakao/connect 접속 → 카카오 동의
//   2) 카카오가 /api/admin/kakao/callback 으로 돌려보냄 → refresh_token 저장
// ---------------------------------------------------------------
app.get("/api/admin/kakao/connect", requireAdmin, (req, res) => {
  if (!kakaoNotify.hasRestKey()) {
    return res.status(400).send("<meta charset='utf-8'>먼저 환경변수 KAKAO_REST_KEY 를 설정하세요.");
  }
  res.redirect(kakaoNotify.authorizeUrl());
});

app.get("/api/admin/kakao/callback", async (req, res) => {
  const code = req.query.code;
  if (!code) return res.status(400).send("<meta charset='utf-8'>인가 코드가 없습니다. 다시 시도하세요.");
  const r = await kakaoNotify.exchangeCode(code);
  if (r.ok) {
    kakaoNotify.notify("✅ 동네사주카페 카카오 알림이 연결되었습니다!\n이제 새 주문·회원가입 때 여기로 알림을 보내드려요.");
    return res.send("<meta charset='utf-8'><div style='font-family:sans-serif;padding:40px;text-align:center;line-height:1.8'>" +
      "<h2>카카오 알림 연결 완료 ✅</h2><p>이제 새 주문·회원가입 시 카카오톡으로 알림을 받습니다.<br>" +
      "카카오톡에 테스트 메시지가 도착했는지 확인해 보세요.</p><a href='/admin.html'>관리자 페이지로</a></div>");
  }
  res.status(400).send("<meta charset='utf-8'><div style='font-family:sans-serif;padding:40px;'>연결 실패: " +
    JSON.stringify(r.error) + "</div>");
});

app.get("/api/admin/kakao/status", requireAdmin, (req, res) => {
  res.json({
    success: true,
    hasRestKey: kakaoNotify.hasRestKey(),
    connected: kakaoNotify.isConnected(),
    redirectUri: kakaoNotify.REDIRECT_URI,
  });
});

app.locals.fulfillOrder = fulfillOrder;

// 결과지 자동 생성 스캐너: 1분마다 예약된 주문을 확인해 PDF 를 자동 생성.
setInterval(autoGenScan, 60 * 1000);
setTimeout(autoGenScan, 15 * 1000); // 부팅 직후 한 번(재시작 후 밀린 주문 따라잡기)

app.listen(PORT, () => {
  console.log(`동네사주카페 서버 실행 중: http://localhost:${PORT}`);
  console.log(`[자동생성] 결과지 자동 생성 대기시간: ${AUTO_GEN_MS / 60000}분`);
  // 서버 시작 시 PDF 렌더 엔진 가용 여부를 점검해 로그로 남긴다(섹션 4).
  probeRenderEngines()
    .then((s) => {
      const ok = [];
      if (s.playwright) ok.push("Playwright(Chromium)");
      if (s.weasyprint) ok.push("WeasyPrint");
      if (s.libreoffice) ok.push("LibreOffice(폴백)");
      if (ok.length === 0) {
        console.warn("[PDF엔진] 사용 가능한 렌더 엔진이 없습니다! " +
          "'python -m playwright install chromium' 또는 'pip install weasyprint' 를 실행하세요.");
        if (s.errors) console.warn("[PDF엔진 상세]", JSON.stringify(s.errors));
      } else {
        console.log("[PDF엔진] 사용 가능:", ok.join(", "),
          s.playwright ? "(주 엔진: Playwright)" : "(주 엔진: " + ok[0] + ")");
      }
    })
    .catch((e) => console.warn("[PDF엔진] 헬스체크 실패:", e.message));
});
