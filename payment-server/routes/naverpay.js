/**
 * ===================================================================
 * routes/naverpay.js - 네이버페이 단건결제 연동
 * ===================================================================
 * 흐름:
 *   1) /api/naverpay/reserve -> 결제 예약 API 호출, reserveId 수신
 *   2) 프론트가 네이버페이 결제창(SDK)을 reserveId로 오픈
 *   3) 결제 완료 후 콜백에서 paymentId 수신
 *   4) /api/naverpay/apply -> 결제 승인 API 호출로 최종 승인 처리
 *   5) 승인 완료 후 PDF 생성 + 이메일 발송(fulfillOrder)을 비동기로 실행
 *
 * ★ 주의: 네이버페이는 가맹점 심사가 완료되어야 파트너센터ID/클라이언트ID/시크릿을
 *   정식 발급받을 수 있습니다. 이 라우트는 심사 완료 후 실제 키를 .env에 넣으면
 *   바로 동작하도록 표준 API 스펙(reserve/apply)에 맞춰 작성되었습니다.
 *   (테스트 환경 키 발급 전까지는 아래 API가 401/인증 오류를 반환하는 것이 정상입니다.)
 *
 * 참고: 네이버페이 개발자센터 결제형 연동 가이드 (https://developer.pay.naver.com)
 * ===================================================================
 */
const express = require("express");
const fetch = require("node-fetch");
const orderStore = require("../orderStore");
const { fulfillOrder } = require("../fulfillOrder");

const router = express.Router();

const NAVERPAY_CLIENT_ID = process.env.NAVERPAY_CLIENT_ID;
const NAVERPAY_CLIENT_SECRET = process.env.NAVERPAY_CLIENT_SECRET;
const NAVERPAY_CHAIN_ID = process.env.NAVERPAY_CHAIN_ID;
const BASE_URL = process.env.BASE_URL || "http://localhost:3000";

// 네이버페이 개발센터(테스트) / 운영 API 엔드포인트
// 테스트: https://dev.apis.naver.com , 운영: https://apis.naver.com
const NAVERPAY_API_BASE = process.env.NAVERPAY_API_BASE || "https://dev.apis.naver.com";

function commonHeaders() {
  return {
    "X-Naver-Client-Id": NAVERPAY_CLIENT_ID,
    "X-Naver-Client-Secret": NAVERPAY_CLIENT_SECRET,
    "Content-Type": "application/json",
  };
}

/**
 * 프론트 결제창(SDK) 초기화에 필요한 공개값을 내려준다.
 * clientId / chainId 를 HTML에 하드코딩하지 않고 .env 에서만 읽도록 한다.
 * (Client Secret 은 절대 내려주지 않는다 — 서버에서만 사용)
 * mode: NAVERPAY_MODE(development|production). 미설정 시 API_BASE 로 자동 판별.
 */
router.get("/config", (req, res) => {
  const mode =
    process.env.NAVERPAY_MODE ||
    (NAVERPAY_API_BASE.includes("dev.apis.naver.com") ? "development" : "production");
  res.json({
    success: true,
    clientId: NAVERPAY_CLIENT_ID || "",
    chainId: NAVERPAY_CHAIN_ID || "",
    mode,
    configured: !!(NAVERPAY_CLIENT_ID && NAVERPAY_CHAIN_ID),
  });
});

/**
 * 결제 예약(reserve): 결제창을 띄우기 전에 주문/금액 정보를 네이버페이 서버에 등록
 */
router.post("/reserve", async (req, res) => {
  const { orderId } = req.body;
  const order = orderStore.getOrder(orderId);
  if (!order) {
    return res.status(404).json({ success: false, message: "주문 정보를 찾을 수 없습니다." });
  }

  try {
    const response = await fetch(
      `${NAVERPAY_API_BASE}/${NAVERPAY_CHAIN_ID}/naverpay/payments/v2.2/reserve`,
      {
        method: "POST",
        headers: {
          ...commonHeaders(),
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({
          merchantPayKey: order.orderId,
          productName: order.orderName,
          totalPayAmount: String(order.amount),
          taxScopeAmount: String(order.amount),
          taxExScopeAmount: "0",
          returnUrl: `${BASE_URL}/api/naverpay/callback?orderId=${encodeURIComponent(order.orderId)}`,
          productItems: JSON.stringify([
            {
              categoryType: "SERVICE",
              categoryId: "ETC",
              uid: order.orderId,
              name: order.orderName,
              count: 1,
            },
          ]),
        }).toString(),
      }
    );

    const data = await response.json();
    if (data.code !== "Success") {
      return res.status(400).json({ success: false, message: data.message || "네이버페이 결제 예약 실패", data });
    }

    orderStore.updateOrder(order.orderId, { pgMeta: { reserveId: data.body.reserveId } });
    res.json({ success: true, reserveId: data.body.reserveId });
  } catch (err) {
    console.error("네이버페이 예약 오류:", err);
    res.status(500).json({ success: false, message: "네이버페이 결제 예약 중 오류: " + err.message });
  }
});

/**
 * 결제 승인(apply): 결제창에서 결제 완료 후 전달받은 paymentId로 최종 승인
 */
router.post("/apply", async (req, res) => {
  const { orderId, paymentId } = req.body;
  const order = orderStore.getOrder(orderId);
  if (!order) {
    return res.status(404).json({ success: false, message: "주문 정보를 찾을 수 없습니다." });
  }

  try {
    const response = await fetch(
      `${NAVERPAY_API_BASE}/${NAVERPAY_CHAIN_ID}/naverpay/payments/v2.2/apply/payment`,
      {
        method: "POST",
        headers: {
          ...commonHeaders(),
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({ paymentId }).toString(),
      }
    );

    const data = await response.json();
    if (data.code !== "Success") {
      orderStore.updateOrder(order.orderId, { status: "FAILED", pgMeta: { ...order.pgMeta, applyError: data } });
      return res.status(400).json({ success: false, message: data.message || "네이버페이 승인 실패", data });
    }

    orderStore.updateOrder(order.orderId, {
      status: "DONE",
      pgMeta: {
        ...order.pgMeta,
        paymentId: data.body.detail.paymentId,
        admissionTypeCode: data.body.detail.admissionTypeCode,
        approvedAt: data.body.detail.admissionYmdt,
      },
    });

    res.json({ success: true, order: orderStore.getOrder(order.orderId), data: data.body });

    // PDF 생성 + 이메일 발송은 비동기로 처리 (프론트는 주문 상태를 폴링)
    fulfillOrder(order.orderId).catch((e) => console.error("주문 이행(fulfillOrder) 실패:", e.message));
  } catch (err) {
    console.error("네이버페이 승인 오류:", err);
    res.status(500).json({ success: false, message: "네이버페이 승인 처리 중 오류: " + err.message });
  }
});

/**
 * 결제창에서 결제 완료 후 돌아오는 콜백 (returnUrl)
 * 실제로는 프론트 SDK가 paymentId를 콜백으로 넘겨주므로, 이 라우트는
 * SDK를 쓰지 않고 순수 리다이렉트 방식으로 연동할 때를 위한 예비 엔드포인트입니다.
 */
router.get("/callback", (req, res) => {
  const { orderId, resultCode, paymentId } = req.query;
  if (resultCode === "Success" && paymentId) {
    res.redirect(`/naverpay-approve.html?orderId=${encodeURIComponent(orderId)}&paymentId=${encodeURIComponent(paymentId)}`);
  } else {
    res.redirect(`/naverpay-fail.html?orderId=${encodeURIComponent(orderId)}`);
  }
});

module.exports = router;
