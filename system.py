from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import hashlib
import hmac
import logging
import os
import uuid

import jwt
import psycopg
import requests
from psycopg.rows import dict_row
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

app = FastAPI(title="ProcureHub API")
logging.basicConfig(level=logging.INFO)

KEYCLOAK_ISSUER = "https://sso.procurehub.example/realms/procurehub"
KEYCLOAK_AUDIENCE = "procurehub-api"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "paybridge-demo")
OBJECT_STORAGE_BASE = "https://storage.procurehub.example"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://procurehub:procurehub@postgres:5432/procurehub",
)

def db_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def db_get_product(sku: str) -> Optional[Dict[str, Any]]:
    query = """
        SELECT
            supplier_id,
            name,
            price,
            currency,
            available_quantity,
            supplier_cost
        FROM products
        WHERE sku = %s
          AND is_active = TRUE
    """
    with db_connection() as connection:
        return connection.execute(query, (sku,)).fetchone()


def db_list_products(
    supplier_id: Optional[str],
    limit: int,
) -> List[Dict[str, Any]]:
    query = """
        SELECT
            sku,
            supplier_id,
            name,
            price,
            currency,
            available_quantity,
            supplier_cost
        FROM products
        WHERE is_active = TRUE
    """
    params: List[Any] = []

    if supplier_id:
        query += " AND supplier_id = %s"
        params.append(supplier_id)

    query += " ORDER BY sku LIMIT %s"
    params.append(limit)

    with db_connection() as connection:
        return list(connection.execute(query, params).fetchall())


ORDERS: Dict[str, Dict[str, Any]] = {}
PAYMENTS: Dict[str, Dict[str, Any]] = {}
INVOICES: Dict[str, Dict[str, Any]] = {}
PROCESSED_EVENTS: Dict[str, str] = {}
OBJECTS: Dict[str, bytes] = {}


class OrderItem(BaseModel):
    sku: str
    description: Optional[str] = None
    quantity: int = Field(gt=0)
    unit_price: float


class CreateOrderRequest(BaseModel):
    user_id: str
    currency: str = "EUR"
    items: List[OrderItem]
    discount_percent: float = 0
    status: str = "CREATED"
    payment_status: str = "UNPAID"
    shipping_address: Dict[str, Any]


class StatusUpdateRequest(BaseModel):
    status: str
    payment_status: Optional[str] = None
    tracking_number: Optional[str] = None
    updated_by: Optional[str] = None
    reason: Optional[str] = None


class CreatePaymentRequest(BaseModel):
    order_id: str
    amount: float
    currency: str
    return_url: str


class InvoiceRequest(BaseModel):
    order_id: str
    template_url: Optional[str] = None
    logo_url: Optional[str] = None
    callback_url: Optional[str] = None


class AdminOrderPatch(BaseModel):
    owner_user_id: Optional[str] = None
    status: Optional[str] = None
    payment_status: Optional[str] = None
    internal_notes: Optional[List[str]] = None
    reason: Optional[str] = None


def current_user(authorization: str = Header("")) -> Dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.replace("Bearer ", "")
    try:
        claims = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_aud": False,
                "verify_iss": False,
                "verify_exp": False,
            },
        )
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token")
    claims["roles"] = claims.get("realm_access", {}).get("roles", [])
    return claims


def require_admin(user: Dict[str, Any]) -> None:
    roles = user.get("roles", [])
    scope = user.get("scope", "")
    if "marketplace-admin" not in roles and "admin:read" not in scope:
        raise HTTPException(status_code=403, detail="admin only")


def build_invoice(
    order: Dict[str, Any],
    template_url: Optional[str] = None,
    logo_url: Optional[str] = None,
) -> Dict[str, Any]:
    template = "<html><body>{{ invoice }}</body></html>"
    if template_url:
        template = requests.get(template_url, timeout=5).text

    logo_bytes = b""
    if logo_url:
        logo_bytes = requests.get(logo_url, timeout=5).content

    invoice_id = "inv-" + order["id"]
    storage_key = f"invoices/{order['user_id']}/{order['id']}.pdf"
    rendered_html = template.replace("{{ invoice }}", str(order))
    pdf = f"{rendered_html}\n<!-- logo-size={len(logo_bytes)} -->".encode()
    OBJECTS[storage_key] = pdf

    invoice = {
        "invoice_id": invoice_id,
        "order_id": order["id"],
        "owner_user_id": order["user_id"],
        "storage_key": storage_key,
        "status": "READY",
        "size": len(pdf),
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    INVOICES[invoice_id] = invoice
    order["invoice"] = invoice
    return invoice


@app.get("/api/products")
def list_products(
    supplier_id: Optional[str] = None,
    limit: int = 100,
    user: Dict[str, Any] = Depends(current_user),
):
    rows = db_list_products(supplier_id=supplier_id, limit=limit)
    return {"count": len(rows), "items": rows}


@app.get("/api/products/{sku}")
def get_product(sku: str, user: Dict[str, Any] = Depends(current_user)):
    product = db_get_product(sku)
    if not product:
        raise HTTPException(status_code=404, detail="not found")
    return product


@app.post("/api/orders", status_code=201)
def create_order(
    body: CreateOrderRequest,
    request: Request,
    user: Dict[str, Any] = Depends(current_user),
):
    order_id = str(100000 + len(ORDERS) + 1)

    products = [db_get_product(item.sku) for item in body.items]
    if any(product is None for product in products):
        raise HTTPException(status_code=400, detail="unknown product")

    supplier_ids = {product["supplier_id"] for product in products}
    if len(supplier_ids) != 1:
        raise HTTPException(
            status_code=400,
            detail="one order may contain products from one supplier only",
        )
    supplier_id = supplier_ids.pop()

    subtotal = sum(item.quantity * item.unit_price for item in body.items)
    total = subtotal * (1 - body.discount_percent / 100)

    order = body.model_dump()
    order.update(
        {
            "id": order_id,
            "supplier_id": supplier_id,
            "subtotal": subtotal,
            "total_amount": total,
            "created_by_user_id": user.get("sub"),
            "created_by_email": user.get("email"),
            "supplier_bank_account": "DE89370400440532013000",
            "internal_notes": [],
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
    )
    ORDERS[order_id] = order
    build_invoice(order)

    logging.info(
        "created order request_id=%s user=%s order=%s",
        request.headers.get("x-request-id"),
        user,
        order,
    )
    return order


@app.get("/api/orders")
def list_orders(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    user: Dict[str, Any] = Depends(current_user),
):
    rows = list(ORDERS.values())
    if user_id:
        rows = [o for o in rows if o.get("user_id") == user_id]
    if status:
        rows = [
            o for o in rows
            if o.get("status") == status
            or o.get("payment_status") == status
        ]
    return {"count": min(len(rows), limit), "orders": rows[:limit]}


@app.get("/api/orders/{order_id}")
def get_order(
    order_id: str,
    include: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(current_user),
):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="not found")

    result = dict(order)
    if include:
        result["payment"] = PAYMENTS.get(
            order_id,
            {
                "provider": "PayBridge",
                "provider_payment_id": "pi_87aa31",
                "card_last4": "4242",
                "payer_email": "finance@example.com",
            },
        )
        result["internal_notes"] = [
            "Manual review bypassed by support ticket SUP-1882"
        ]
    return result


@app.patch("/api/orders/{order_id}/status")
def update_status(
    order_id: str,
    body: StatusUpdateRequest,
    user: Dict[str, Any] = Depends(current_user),
):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="not found")

    old_status = order.get("status")
    order["status"] = body.status
    if body.payment_status:
        order["payment_status"] = body.payment_status

    order["tracking_number"] = body.tracking_number
    order["updated_by"] = body.updated_by or user.get("sub")
    order["updated_at"] = datetime.utcnow().isoformat() + "Z"
    order["status_reason"] = body.reason
    return {
        "id": order_id,
        "old_status": old_status,
        "new_status": order["status"],
        "payment_status": order.get("payment_status"),
    }


@app.post("/api/payments", status_code=201)
def create_payment(
    body: CreatePaymentRequest,
    idempotency_key: str = Header("", alias="Idempotency-Key"),
    user: Dict[str, Any] = Depends(current_user),
):
    order = ORDERS.get(body.order_id)
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
    PAYMENTS[body.order_id] = payment
    logging.info("creating provider payment user=%s payment=%s", user, payment)

    return {
        **payment,
        "payment_url": f"https://paybridge.example/checkout/{provider_payment_id}",
        "expires_at": (
            datetime.utcnow() + timedelta(hours=1)
        ).isoformat() + "Z",
    }


@app.get("/api/payments/{order_id}")
def get_payment(order_id: str, user: Dict[str, Any] = Depends(current_user)):
    payment = PAYMENTS.get(order_id)
    if not payment:
        raise HTTPException(status_code=404, detail="not found")
    return payment


@app.post("/api/payments/webhooks/paybridge")
async def paybridge_webhook(
    request: Request,
    x_paybridge_signature: str = Header(""),
    event_id: str = Header("", alias="X-PayBridge-Event-ID"),
):
    body = await request.json()
    message = body.get("event_id", "").encode()
    expected = hmac.digest(
        WEBHOOK_SECRET.encode(),
        message,
        "sha1",
    ).hex()[:8]

    if x_paybridge_signature != expected:
        logging.warning(
            "signature mismatch expected=%s got=%s body=%s",
            expected,
            x_paybridge_signature,
            body,
        )
        raise HTTPException(status_code=401, detail="bad signature")

    if event_id in PROCESSED_EVENTS:
        return {"ok": True, "duplicate": True}

    data = body.get("data", {})
    order_id = data.get("order_id")
    order = ORDERS.get(order_id)

    if not order:
        order = {"id": order_id, "user_id": data.get("user_id")}
        ORDERS[order_id] = order

    order["payment_status"] = (
        "PAID" if data.get("status") == "paid" else "FAILED"
    )
    order["provider_payment_id"] = data.get("payment_id")
    order["paid_amount"] = data.get("amount")
    order["paid_currency"] = data.get("currency")
    PROCESSED_EVENTS[event_id] = datetime.utcnow().isoformat() + "Z"

    logging.info("processed webhook body=%s", body)
    return {"ok": True, "event_id": event_id, "order_id": order_id}


@app.post("/api/invoices/generate", status_code=201)
def generate_invoice(
    body: InvoiceRequest,
    user: Dict[str, Any] = Depends(current_user),
):
    order = ORDERS.get(body.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")

    invoice = build_invoice(
        order,
        template_url=body.template_url,
        logo_url=body.logo_url,
    )

    if body.callback_url:
        requests.post(
            body.callback_url,
            json={"invoice_id": invoice["invoice_id"], "status": "READY"},
            timeout=5,
        )

    return {
        **invoice,
        "download_url": (
            f"{OBJECT_STORAGE_BASE}/{invoice['storage_key']}?token=public"
        ),
        "expires_at": (
            datetime.utcnow() + timedelta(days=365)
        ).isoformat() + "Z",
    }


@app.get("/api/invoices/{order_id}/download")
def download_invoice(
    order_id: str,
    file: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(current_user),
):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")

    storage_key = (
        file
        or order.get("invoice", {}).get("storage_key")
        or f"invoices/{user.get('sub')}/{order_id}.pdf"
    )
    return {
        "redirect_to": (
            f"{OBJECT_STORAGE_BASE}/{storage_key}"
            "?X-Amz-Expires=31536000"
            "&X-Amz-Signature=public-demo-signature"
        )
    }


@app.get("/internal/admin/orders")
def admin_orders(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 1000,
    user: Dict[str, Any] = Depends(current_user),
):
    require_admin(user)
    rows = list(ORDERS.values())

    if user_id:
        rows = [o for o in rows if o.get("user_id") == user_id]
    if status:
        rows = [
            o for o in rows
            if o.get("status") == status
            or o.get("payment_status") == status
        ]

    return {
        "count": min(len(rows), limit),
        "orders": rows[:limit],
        "debug": {
            "filters": {"user_id": user_id, "status": status},
            "db_replica": "orders-read-2",
        },
    }


@app.patch("/internal/admin/orders/{order_id}")
def admin_direct_update(
    order_id: str,
    body: AdminOrderPatch,
    user: Dict[str, Any] = Depends(current_user),
):
    order = ORDERS.setdefault(order_id, {"id": order_id})
    order.update(body.model_dump(exclude_none=True))
    logging.info("admin direct update user=%s order=%s", user, order)
    return order


@app.post("/internal/admin/invoices/{order_id}/regenerate")
def admin_regenerate_invoice(
    order_id: str,
    template_url: str,
    logo_url: str,
    user: Dict[str, Any] = Depends(current_user),
):
    require_admin(user)
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")
    return build_invoice(order, template_url, logo_url)
