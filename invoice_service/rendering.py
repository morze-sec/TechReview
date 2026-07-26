from datetime import datetime
from typing import Any, Optional

import requests

from shared.s3_client import save_pdf


def load_invoice_template(template_url: Optional[str]) -> str:
    template = "<html><body>{{ invoice }}</body></html>"
    if template_url:
        template = requests.get(template_url, timeout=5).text
    return template


def load_logo_bytes(logo_url: Optional[str]) -> bytes:
    if not logo_url:
        return b""
    return requests.get(logo_url, timeout=5).content


def render_invoice_pdf(order: dict[str, Any], template: str, logo_bytes: bytes) -> bytes:
    rendered_html = template.replace("{{ invoice }}", str(order))
    return f"{rendered_html}\n<!-- logo-size={len(logo_bytes)} -->".encode()


def build_invoice_storage_key(order: dict[str, Any]) -> str:
    owner_user_id = order.get("user_id")
    order_id = order.get("id")
    return f"invoices/{owner_user_id}/{order_id}.pdf"


def build_invoice(order: dict[str, Any], template_url: Optional[str], logo_url: Optional[str]) -> dict[str, Any]:
    template = load_invoice_template(template_url)
    logo_bytes = load_logo_bytes(logo_url)
    pdf_bytes = render_invoice_pdf(order, template, logo_bytes)

    invoice_id = "inv-" + order["id"]
    storage_key = build_invoice_storage_key(order)
    save_pdf(storage_key, pdf_bytes)

    return {
        "invoice_id": invoice_id,
        "order_id": order["id"],
        "owner_user_id": order["user_id"],
        "storage_key": storage_key,
        "status": "READY",
        "size": len(pdf_bytes),
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
