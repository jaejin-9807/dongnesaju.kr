/**
 * ===================================================================
 * routes/toss.js - 토스페이먼츠 V2 결제위젯 연동
 * ===================================================================
 * 흐름:
 *   1) 프론트(payment-toss.html)에서 결제위젯으로 결제창을 띄움
 *   2) 사용자가 결제 완료 -> successUrl로 리다이렉트 (paymentKey, orderId, amount 전달)
 *   3) 프론트가 이 값을 그대로 서버(/api/toss/confirm)에 전달
 *   4) 서버가 토스페이먼츠 결제 승인 API를 호출해서 최종 승인 처리
 *   5) 승인 완료 후 PDF 생성 + 이메일 발송(fulfillOrder)을 비동기로 실행
 *
 * 참고 문서: https://docs.tosspayments.com/guides/v2/get-started/payment-flow
 * ===================================================================
 */
const express = require("express");
const fetch = require("node-fetch");
const orderStore = require("../orderStore");
const { fulfillOrder } = require("../fulfillOrder");

const router = express.Router();

const TOSS_SECRET_KEY = process.env.TOSS_SECRET_KEY;
const TOSS_API_BASE = "https://api.tosspayments.com/v1/payments";

function getAuthHeader() {
  const encoded = Buffer.from(`${TOSS_SECRET_KEY}:`).toString("base64");
  return `Basic ${encoded}`;
}

// 프론트에 클라이언트 키를 안전하게 내려주는 엔드포인트
// (시크릿 키는 절대 프론트로 내려가지 않습니다)
router.get("/client-key", (req, res) => {
  res.json({ clientKey: process.env.TOSS_CLIENT_KEY });
});

/**
 * 결제 승인 요청
 * 프론트에서 successUrl 리다이렉트 후 전달받은 paymentKey/orderId/amount를 그대로 받아
 * 토스페이먼츠 서버에 최종 승인을 요청한다.
 *
 * 반드시 우리 서버에 저장해둔 주문 금액과, 토스에서 돌아온 amount가 같은지
 * 먼저 검증한 뒤 승인 요청을 보낸다. (금액 위변조 방지 - 토스페이먼츠 필수 가이드)
 */
router.post("/confirm", async (req, res) => {
  const { paymentKey, orderId, amount } = req.body;

  if (!paymentKey || !orderId || !amount) {
    return res.status(400).json({ success: false, message: "paymentKey, orderId, amount는 필수입니다." });
  }

  const order = orderStore.getOrder(orderId);
  if (!order) {
    return res.status(404).json({ success: false, message: "주문 정보를 찾을 수 없습니다." });
  }
  if (Number(order.amount) !== Number(amount)) {
    return res.status(400).json({ success: false, message: "결제 금액이 주문 금액과 일치하지 않습니다." });
  }

  try {
    const response = await fetch(`${TOSS_API_BASE}/confirm`, {
      method: "POST",
      headers: {
        Authorization: getAuthHeader(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ paymentKey, orderId, amount: Number(amount) }),
    });

    const data = await response.json();

    if (!response.ok) {
      orderStore.updateOrder(orderId, { status: "FAILED", pgMeta: data });
      return res.status(response.status).json({ success: false, message: data.message || "결제 승인 실패", data });
    }

    orderStore.updateOrder(orderId, {
      status: "DONE",
      pgMeta: {
        paymentKey: data.paymentKey,
        method: data.method,
        approvedAt: data.approvedAt,
        receipt: data.receipt,
      },
    });

    res.json({ success: true, order: orderStore.getOrder(orderId), payment: data });

    // PDF 생성 + 이메일 발송은 시간이 걸릴 수 있으므로 응답 후 비동기로 처리한다.
    // 프론트는 /api/orders/:orderId 를 폴링해서 pdfPath/emailSent 상태를 확인한다.
    fulfillOrder(orderId).catch((e) => console.error("주문 이행(fulfillOrder) 실패:", e.message));
  } catch (err) {
    console.error("토스 결제 승인 오류:", err);
    res.status(500).json({ success: false, message: "결제 승인 처리 중 오류가 발생했습니다: " + err.message });
  }
});

module.exports = router;
