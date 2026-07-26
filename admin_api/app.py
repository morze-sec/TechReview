from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException

from shared.auth import current_user, require_admin
from shared.models import AdminOrderPatch
from shared.order_repository import get_order, list_orders, save_order

from invoice_service.rendering import build_invoice
from invoice_service.repository import save_invoice

app = FastAPI(title="ProcureHub Internal Admin API")


@app.get("/internal/admin/orders")
def admin_orders(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 1000,
    user: dict[str, Any] = Depends(current_user),
):
    require_admin(user)
    rows = list_orders(user_id=user_id, status=status, limit=limit)

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
    user: dict[str, Any] = Depends(current_user),
):
    order = get_order(order_id) or {"id": order_id}
    order.update(body.model_dump(exclude_none=True))
    save_order(order)
    return order


@app.post("/internal/admin/invoices/{order_id}/regenerate")
def admin_regenerate_invoice(
    order_id: str,
    template_url: str,
    logo_url: str,
    user: dict[str, Any] = Depends(current_user),
):
    require_admin(user)
    order = get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")

    invoice = build_invoice(order, template_url, logo_url)
    save_invoice(invoice)
    return invoice
