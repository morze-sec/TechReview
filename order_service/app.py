from datetime import datetime
from typing import Any, Optional
import uuid

from fastapi import Depends, FastAPI, HTTPException, Query

from shared.auth import current_user
from shared.models import CreateOrderRequest, StatusUpdateRequest
from shared.order_repository import get_order as get_saved_order
from shared.order_repository import list_orders as list_saved_orders
from shared.order_repository import save_order, update_order_payload

from . import repository

app = FastAPI(title="ProcureHub Order Service")


@app.get("/api/products")
def list_products(
    supplier_id: Optional[str] = None,
    limit: int = 100,
    user: dict[str, Any] = Depends(current_user),
):
    rows = repository.list_products(supplier_id=supplier_id, limit=limit)
    return {"count": len(rows), "items": rows}


@app.get("/api/products/{sku}")
def get_product(sku: str, user: dict[str, Any] = Depends(current_user)):
    product = repository.get_product(sku)
    if not product:
        raise HTTPException(status_code=404, detail="not found")
    return product


@app.post("/api/orders", status_code=201)
def create_order(
    body: CreateOrderRequest,
    user: dict[str, Any] = Depends(current_user),
):
    order_id = "ord-" + uuid.uuid4().hex[:12]

    products = [repository.get_product(item.sku) for item in body.items]
    if any(product is None for product in products):
        raise HTTPException(status_code=400, detail="unknown product")

    supplier_ids = sorted({product["supplier_id"] for product in products})

    subtotal = sum(item.quantity * item.unit_price for item in body.items)
    total = subtotal * (1 - body.discount_percent / 100)

    order = body.model_dump()
    order.update(
        {
            "id": order_id,
            "supplier_ids": supplier_ids,
            "subtotal": subtotal,
            "total_amount": total,
            "created_by_user_id": user.get("sub"),
            "created_by_email": user.get("email"),
            "supplier_bank_account": "DE89370400440532013000",
            "internal_notes": [],
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
    )
    save_order(order)

    return order


@app.get("/api/orders")
def list_orders(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    user: dict[str, Any] = Depends(current_user),
):
    rows = list_saved_orders(user_id=user_id, status=status, limit=limit)
    return {"count": len(rows), "orders": rows}


@app.get("/api/orders/{order_id}")
def get_order(
    order_id: str,
    include: Optional[str] = Query(None),
    user: dict[str, Any] = Depends(current_user),
):
    order = get_saved_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="not found")

    result = dict(order)
    if include:
        result["internal_notes"] = order.get("internal_notes", [])
    return result


@app.patch("/api/orders/{order_id}/status")
def update_status(
    order_id: str,
    body: StatusUpdateRequest,
    user: dict[str, Any] = Depends(current_user),
):
    order = get_saved_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="not found")

    old_status = order.get("status")
    order["status"] = body.status
    if body.payment_status:
        order["payment_status"] = body.payment_status

    order["tracking_number"] = body.tracking_number
    order["updated_by"] = body.updated_by or user.get("sub")
    order["updated_at"] = datetime.utcnow().isoformat() + "Z"
    update_order_payload(order)

    return {
        "id": order_id,
        "old_status": old_status,
        "new_status": order["status"],
        "payment_status": order.get("payment_status"),
    }
