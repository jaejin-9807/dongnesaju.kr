/**
 * ===================================================================
 * routes/kakaopay.js - 카카오페이 단건결제 연동
 * ===================================================================
 * 흐름:
 *   1) /api/kakaopay/ready  -> 결제 준비 API 호출, 리다이렉트 URL 3종 수신
 *   2) 프론트가 next_redirect_pc_url(또는 mobile) 로 이동 -> 사용자가 카카오톡 결제 진행
 *   3) 결제 성공 시 approval_url(우리 서버의 /api/kakaopay/success)로 pg_token과 함께 리다이렉트
 *   4) /api/kakaopay/success 에서 승인(approve) API 호출로 결제 완료 처리
 *   5) 승인 완료 후 PDF 생성 + 이메일 발송(fulfillOrder)을 비동기로 실행
 *
 * 참고: 카카오페이 결제 준비 API는 "Authorization: SECRET_KEY {키}" 헤더를 사용합니다.
 * ===================================================================
 */
const express = require("express");
const fetch = require("node-fetch");
const orderStore = require("../orderStore");
const { fulfillOrder } = require("../fulfillOrder");

const router = express.Router();

const KAKAOPAY_ADMIN_KEY = process.env.KAKAOPAY_ADMIN_KEY;
const KAKAOPAY_CID = process.env.KAKAOPAY_CID || "TC0ONETIME";
const BASE_URL = process.env.BASE_URL || "http://localhost:3000";
const KAKAOPAY_API_BASE = "https://open-api.kakaopay.com/online/v1/payment";

function authHeader() {
  return `SECRET_KEY ${KAKAOPAY_ADMIN_KEY}`;
}

/**
 * 결제 준비: 우리 서버에 만들어둔 orderId를 기준으로 카카오페이 ready API 호출
 */
router.post("/ready", async (req, res) => {
  const { orderId } = req.body;
  const order = orderStore.getOrder(orderId);
  if (!order) {
    return res.status(404).json({ success: false, message: "주문 정보를 찾을 수 없습니다." });
  }

  try {
    const response = await fetch(`${KAKAOPAY_API_BASE}/ready`, {
      method: "POST",
      headers: {
        Authorization: authHeader(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        cid: KAKAOPAY_CID,
        partner_order_id: order.orderId,
        partner_user_id: order.customerEmail || order.customerName || "guest",
        item_name: order.orderName,
        quantity: "1",
        total_amount: String(order.amount),
        vat_amount: String(Math.round(order.amount / 11)),
        tax_free_amount: "0",
        approval_url: `${BASE_URL}/api/kakaopay/success?orderId=${encodeURIComponent(order.orderId)}`,
        fail_url: `${BASE_URL}/kakaopay-fail.html?orderId=${encodeURIComponent(order.orderId)}`,
        cancel_url: `${BASE_URL}/kakaopay-fail.html?orderId=${encodeURIComponent(order.orderId)}&canceled=1`,
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      return res.status(response.status).json({ success: false, message: data.msg || "카카오페이 결제 준비 실패", data });
    }

    // tid는 승인 단계에서 필요하므로 주문에 저장해둔다
    orderStore.updateOrder(order.orderId, { pgMeta: { tid: data.tid } });

    res.json({ success: true, ...data });
  } catch (err) {
    console.error("카카오페이 ready 오류:", err);
    res.status(500).json({ success: false, message: "카카오페이 결제 준비 중 오류: " + err.message });
  }
});

/**
 * 결제 승인: approval_url로 리다이렉트되어 오면 pg_token을 받아 승인 API 호출
 */
router.get("/success", async (req, res) => {
  const { orderId, pg_token } = req.query;
  const order = orderStore.getOrder(orderId);

  if (!order || !order.pgMeta || !order.pgMeta.tid) {
    return res.redirect(`/kakaopay-fail.html?orderId=${encodeURIComponent(orderId || "")}&message=${encodeURIComponent("주문 정보를 찾을 수 없습니다.")}`);
  }

  try {
    const response = await fetch(`${KAKAOPAY_API_BASE}/approve`, {
      method: "POST",
      headers: {
        Authorization: authHeader(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        cid: KAKAOPAY_CID,
        tid: order.pgMeta.tid,
        partner_order_id: order.orderId,
        partner_user_id: order.customerEmail || order.customerName || "guest",
        pg_token,
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      orderStore.updateOrder(order.orderId, { status: "FAILED", pgMeta: { ...order.pgMeta, approveError: data } });
      return res.redirect(`/kakaopay-fail.html?orderId=${encodeURIComponent(orderId)}&message=${encodeURIComponent(data.msg || "승인 실패")}`);
    }

    orderStore.updateOrder(order.orderId, {
      status: "DONE",
      pgMeta: {
        ...order.pgMeta,
        aid: data.aid,
        approvedAt: data.approved_at,
        paymentMethodType: data.payment_method_type,
      },
    });

    res.redirect(`/kakaopay-success.html?orderId=${encodeURIComponent(orderId)}`);

    // PDF 생성 + 이메일 발송은 비동기로 처리 (프론트는 주문 상태를 폴링)
    fulfillOrder(order.orderId).catch((e) => console.error("주문 이행(fulfillOrder) 실패:", e.message));
  } catch (err) {
    console.error("카카오페이 승인 오류:", err);
    res.redirect(`/kakaopay-fail.html?orderId=${encodeURIComponent(orderId)}&message=${encodeURIComponent(err.message)}`);
  }
});

module.exports = router;
