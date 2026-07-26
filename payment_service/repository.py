from typing import Any

from shared.db import execute


def save_payment(payment: dict[str, Any]) -> None:
    execute(
        """
        INSERT INTO payments (
            payment_id, provider_payment_id, order_id, amount, currency,
            status, payload_json, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, now())
        ON CONFLICT (payment_id) DO UPDATE
        SET payload_json = EXCLUDED.payload_json,
            status = EXCLUDED.status
        """,
        [
            payment["payment_id"],
            payment["provider_payment_id"],
            payment["order_id"],
            payment["amount"],
            payment["currency"],
            payment["status"],
            payment,
        ],
    )
