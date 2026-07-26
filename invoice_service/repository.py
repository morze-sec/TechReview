from typing import Any

from shared.db import execute


def save_invoice(invoice: dict[str, Any]) -> None:
    execute(
        """
        INSERT INTO invoices (
            invoice_id, order_id, owner_user_id, storage_key,
            status, size, payload_json, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, now())
        ON CONFLICT (invoice_id) DO UPDATE
        SET storage_key = EXCLUDED.storage_key,
            status = EXCLUDED.status,
            size = EXCLUDED.size,
            payload_json = EXCLUDED.payload_json
        """,
        [
            invoice["invoice_id"],
            invoice["order_id"],
            invoice["owner_user_id"],
            invoice["storage_key"],
            invoice["status"],
            invoice["size"],
            invoice,
        ],
    )
