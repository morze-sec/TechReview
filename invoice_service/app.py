from datetime import datetime, timedelta
from typing import Any

import requests
from fastapi import Depends, FastAPI, HTTPException

from shared.auth import current_user
from shared.models import InvoiceRequest
from shared.order_repository import get_order
from shared.s3_client import public_object_url

from . import repository
from .rendering import build_invoice

app = FastAPI(title="ProcureHub Invoice Service")


@app.post("/api/invoices/generate", status_code=201)
def generate_invoice(
    body: InvoiceRequest,
    user: dict[str, Any] = Depends(current_user),
):
    order = get_order(body.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")

    invoice = build_invoice(
        order,
        template_url=body.template_url,
        logo_url=body.logo_url,
    )
    repository.save_invoice(invoice)

    if body.callback_url:
        requests.post(
            body.callback_url,
            json={"invoice_id": invoice["invoice_id"], "status": "READY"},
            timeout=5,
        )

    return {
        **invoice,
        "download_url": public_object_url(invoice["storage_key"]),
        "expires_at": (datetime.utcnow() + timedelta(days=365)).isoformat() + "Z",
    }
