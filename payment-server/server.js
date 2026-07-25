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
const { calculateSaju, generatePdf, probeRenderEngines } = require("./sajuEngine");
const { fulfillOrder, PDF_OUTPUT_DIR } = require("./fulfillOrder");
const { sendResultToCustomer, sendResultSmsToCustomer } = require("./mailer");

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
  // 단품 운세풀이 29,800원 / 궁합(2인) 정가 59,600원 → 할인가 55,000원
  // 이벤트 사주풀이 = 0원(SNS 무료 이벤트) / 단품 29,800원 / 궁합(2인) 할인가 55,000원
  const PRICES = { "이벤트 사주풀이": 0, "프리미엄 사주풀이": 29800, "궁합사주": 55000 };
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
    year: Number(person.year),
    month: Number(person.month),
    day: Number(person.day),
    hour: person.hour != null && person.hour !== "" ? Number(person.hour) : 0,
    minute: person.minute != null && person.minute !== "" ? Number(person.minute) : 0,
  };
}

app.post("/api/orders/register", requireCustomer, async (req, res) => {
  const {
    productName, productType,
    customerName, customerNameHanja, customerEmail, customerPhone,
    person1, person2,
  } = req.body;

  if (!productName || !customerName || !customerEmail || !person1) {
    return res.status(400).json({ success: false, message: "필수 항목(상품명/이름/이메일/생년월일)이 비어 있습니다." });
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
  const fs2 = require("fs");
  if (!order.pdfPath || !fs2.existsSync(order.pdfPath)) {
    return res.status(404).json({ success: false, message: "아직 결과지가 준비되지 않았습니다." });
  }
  const meta = buildPdfMeta(order);
  const filename = order.pdfFilename ||
    (sanitizeFilename(`${meta.customerName}_${meta.reportType}_${meta.reportYear}`) + ".pdf");
  res.setHeader("Content-Disposition", `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`);
  res.setHeader("Content-Type", "application/pdf");
  res.sendFile(order.pdfPath);
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
    const updated = await app.locals.fulfillOrder(order.orderId);
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

app.post("/api/admin/orders/:orderId/generate-pdf", requireAdmin, async (req, res) => {
  const order = orderStore.getOrder(req.params.orderId);
  if (!order) return res.status(404).json({ success: false, message: "주문을 찾을 수 없습니다." });
  if (!order.sajuResult) return res.status(400).json({ success: false, message: "사주 계산 결과가 없습니다." });

  try {
    // 궁합 상품인데 사주 결과에 궁합 계산이 없으면, 상대방(person2)을 포함해 다시 계산하여
    // 궁합 명식/근거가 PDF에 반영되도록 한다. (person2 전달 누락 보완)
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
    });
    res.json({ success: true, order: updated, render: result });
  } catch (e) {
    console.error("관리자 PDF 생성 오류:", e.message);
    res.status(500).json({ success: false, message: "PDF 생성 중 오류가 발생했습니다: " + e.message });
  }
});

app.get("/api/admin/orders/:orderId/pdf", requireAdmin, (req, res) => {
  const order = orderStore.getOrder(req.params.orderId);
  if (!order || !order.pdfPath) {
    return res.status(404).json({ success: false, message: "결과지가 아직 준비되지 않았습니다." });
  }
  const meta = buildPdfMeta(order);
  const filename = order.pdfFilename ||
    (sanitizeFilename(`${meta.customerName}_${meta.reportType}_${meta.reportYear}`) + ".pdf");
  res.setHeader("Content-Disposition", `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`);
  res.setHeader("Content-Type", "application/pdf");
  res.sendFile(order.pdfPath);
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

app.locals.fulfillOrder = fulfillOrder;

app.listen(PORT, () => {
  console.log(`동네사주카페 서버 실행 중: http://localhost:${PORT}`);
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
