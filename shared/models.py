from typing import Any, Optional

from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    sku: str
    quantity: int = Field(gt=0)
    unit_price: float


class CreateOrderRequest(BaseModel):
    user_id: str
    currency: str = "EUR"
    items: list[OrderItem]
    discount_percent: float = 0
    status: str = "CREATED"
    payment_status: str = "UNPAID"
    shipping_address: dict[str, Any]


class StatusUpdateRequest(BaseModel):
    status: str
    payment_status: Optional[str] = None
    tracking_number: Optional[str] = None
    updated_by: Optional[str] = None


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
    internal_notes: Optional[list[str]] = None
