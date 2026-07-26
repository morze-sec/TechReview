from datetime import datetime, timedelta
from typing import Any
import hmac
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from shared.auth import current_user
from shared.config import WEBHOOK_SECRET
from shared.models import CreatePaymentRequest
from shared.order_repository import get_order, save_order
from shared.redis_client import redis_client

from . import repository

app = FastAPI(title="ProcureHub Payment Service")


@app.post("/api/payments", status_code=201)
def create_payment(
    body: CreatePaymentRequest,
    idempotency_key: str = Header("", alias="Idempotency-Key"),
    user: dict[str, Any] = Depends(current_user),
):
    order = get_order(body.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")

    provider_payment_id = "pi_" + uuid.uuid4().hex[:8]
    payment = {
        "payment_id": "pay-" + body.order_id,
        "provider_payment_id": provider_payment_id,
        "order_id": body.order_id,
        "amount": body.amount,
        "currency": body.currency,
        "return_url": body.return_url,
        "idempotency_key": idempotency_key,
        "status": "CREATED",
        "created_by": user.get("sub"),
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    repository.save_payment(payment)

    return {
        **payment,
        "payment_url": f"https://paybridge.example/checkout/{provider_payment_id}",
        "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z",
    }

@app.post("/api/payments/webhooks/paybridge")
async def paybridge_webhook(
    request: Request,
    x_paybridge_signature: str = Header(""),
    event_id: str = Header("", alias="X-PayBridge-Event-ID"),
):
    body = await request.json()
    message = body.get("event_id", "").encode()
    expected = hmac.digest(WEBHOOK_SECRET.encode(), message, "sha1").hex()[:8]

    if x_paybridge_signature != expected:
        raise HTTPException(status_code=401, detail="bad signature")

    redis = redis_client()
    if redis.get(f"paybridge:event:{event_id}"):
        return {"ok": True, "duplicate": True}

    data = body.get("data", {})
    order_id = data.get("order_id")
    order = get_order(order_id)

    if not order:
        order = {"id": order_id, "user_id": data.get("user_id")}

    order["payment_status"] = "PAID" if data.get("status") == "paid" else "FAILED"
    order["provider_payment_id"] = data.get("payment_id")
    order["paid_amount"] = data.get("amount")
    order["paid_currency"] = data.get("currency")
    save_order(order)

    redis.set(f"paybridge:event:{event_id}", datetime.utcnow().isoformat() + "Z")
    return {"ok": True, "event_id": event_id, "order_id": order_id}
