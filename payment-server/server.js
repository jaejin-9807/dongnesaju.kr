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
    reportType: isEvent ? "이벤트 무료 사주" : (isCouple ? "궁합 분석" : (order.orderName || "종합 사주 분석")),
    product: order.orderName || "",   // 상품별 결과지 섹션 선택에 사용
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
    person1, person2,
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
    res.status(500).json({ success: false, message: "메일 발송 중 오류가 발생했습니다: " + e.message });
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
