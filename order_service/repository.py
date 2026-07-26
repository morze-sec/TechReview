from typing import Any, Optional

from shared.db import fetch_all, fetch_one


def get_product(sku: str) -> Optional[dict[str, Any]]:
    return fetch_one(
        """
        SELECT supplier_id, name, price, currency, available_quantity, supplier_cost
        FROM products
        WHERE sku = %s AND is_active = TRUE
        """,
        [sku],
    )


def list_products(supplier_id: Optional[str], limit: int) -> list[dict[str, Any]]:
    query = """
        SELECT sku, supplier_id, name, price, currency, available_quantity, supplier_cost
        FROM products
        WHERE is_active = TRUE
    """
    params: list[Any] = []

    if supplier_id:
        query += " AND supplier_id = %s"
        params.append(supplier_id)

    query += " ORDER BY sku LIMIT %s"
    params.append(limit)
    return fetch_all(query, params)
