from typing import Any, Optional

from .db import execute, fetch_all, fetch_one


def get_order(order_id: str) -> Optional[dict[str, Any]]:
    row = fetch_one("SELECT payload_json FROM orders WHERE id = %s", [order_id])
    return row["payload_json"] if row else None


def list_orders(user_id: Optional[str], status: Optional[str], limit: int) -> list[dict[str, Any]]:
    query = "SELECT payload_json FROM orders WHERE TRUE"
    params: list[Any] = []

    if user_id:
        query += " AND user_id = %s"
        params.append(user_id)
    if status:
        query += " AND (status = %s OR payment_status = %s)"
        params.extend([status, status])

    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    return [row["payload_json"] for row in fetch_all(query, params)]


def save_order(order: dict[str, Any]) -> None:
    execute(
        """
        INSERT INTO orders (
            id, user_id, status, payment_status, currency,
            subtotal, total_amount, payload_json, internal_notes, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
        ON CONFLICT (id) DO UPDATE
        SET user_id = COALESCE(EXCLUDED.user_id, orders.user_id),
            status = COALESCE(EXCLUDED.status, orders.status),
            payment_status = COALESCE(EXCLUDED.payment_status, orders.payment_status),
            currency = COALESCE(EXCLUDED.currency, orders.currency),
            subtotal = COALESCE(EXCLUDED.subtotal, orders.subtotal),
            total_amount = COALESCE(EXCLUDED.total_amount, orders.total_amount),
            payload_json = EXCLUDED.payload_json,
            internal_notes = COALESCE(EXCLUDED.internal_notes, orders.internal_notes),
            updated_at = now()
        """,
        [
            order["id"],
            order.get("user_id"),
            order.get("status"),
            order.get("payment_status"),
            order.get("currency"),
            order.get("subtotal"),
            order.get("total_amount"),
            order,
            order.get("internal_notes", []),
        ],
    )


def update_order_payload(order: dict[str, Any]) -> None:
    execute(
        """
        UPDATE orders
        SET status = %s,
            payment_status = %s,
            payload_json = %s::jsonb,
            updated_at = now()
        WHERE id = %s
        """,
        [order.get("status"), order.get("payment_status"), order, order["id"]],
    )
