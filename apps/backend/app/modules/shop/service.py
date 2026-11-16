"""Shop: products with stock, orders that can never oversell, status history, bulk orders with a delivery date.

Stock rule (Blueprint 8.4): `UPDATE products SET stock = stock - :qty WHERE id = :id AND stock >= :qty`. The
condition runs inside the row update, so concurrent orders cannot take the same unit. Cancelling restores stock.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, LargeBinary, String, func, select, update
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core import crypto, rate_limit
from app.core.database import Base
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.events import emit
from app.core.ids import uuid7
from app.modules.accounts.models import User
from app.modules.business import service as business
from app.modules.media import service as media
from app.modules.media.service import AssetOut

MAX_ITEMS = 50


class Product(Base):
    __tablename__ = "products"
    __table_args__ = {"schema": "shop"}  # noqa: RUF012
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    sku: Mapped[str | None] = mapped_column(String(40))
    price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    media: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = {"schema": "shop"}  # noqa: RUF012
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="placed")
    payment_status: Mapped[str] = mapped_column(String(12), nullable=False, default="unpaid")
    total_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fulfilment: Mapped[str] = mapped_column(String(10), nullable=False, default="pickup")
    address_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    wanted_on: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = {"schema": "shop"}  # noqa: RUF012
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    unit_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    __table_args__ = {"schema": "shop"}  # noqa: RUF012
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(12))
    to_status: Mapped[str] = mapped_column(String(12), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


OrderStatus = Literal["placed", "confirmed", "ready", "shipped", "delivered", "cancelled"]
SELLER_FLOW: dict[str, set[str]] = {
    "placed": {"confirmed", "cancelled"},
    "confirmed": {"ready", "shipped", "cancelled"},
    "ready": {"delivered", "cancelled"},
    "shipped": {"delivered"},
}
CUSTOMER_CANCELLABLE = {"placed"}


class ProductIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    sku: str | None = Field(default=None, max_length=40)
    price_paise: int = Field(ge=0, le=100_000_000)
    stock: int = Field(ge=0, le=1_000_000)
    media_ids: list[uuid.UUID] = Field(default_factory=list, max_length=8)
    active: bool = True


class ProductOut(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    description: str | None
    sku: str | None
    price_paise: int
    stock: int
    in_stock: bool
    media: list[AssetOut]
    active: bool


class OrderLine(BaseModel):
    product_id: uuid.UUID
    qty: int = Field(ge=1, le=1000)


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_id: uuid.UUID
    items: list[OrderLine] = Field(min_length=1, max_length=MAX_ITEMS)
    fulfilment: Literal["pickup", "delivery"] = "pickup"
    address: str | None = Field(default=None, max_length=500)
    wanted_on: date | None = Field(default=None, description="Bulk orders: the date the customer needs it")
    note: str | None = Field(default=None, max_length=500)


class OrderItemOut(BaseModel):
    product_id: uuid.UUID
    name: str
    unit_price_paise: int
    qty: int


class OrderOut(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    customer_id: uuid.UUID
    status: str
    payment_status: str
    total_paise: int
    fulfilment: str
    wanted_on: date | None
    note: str | None
    items: list[OrderItemOut]
    created_at: datetime
    address: str | None = None


async def _product_out(db: AsyncSession, p: Product, *, owner: bool) -> ProductOut:
    assets = await media.public_views(db, [uuid.UUID(m) for m in p.media])
    return ProductOut(
        id=p.id,
        business_id=p.business_id,
        name=p.name,
        description=p.description,
        sku=p.sku,
        price_paise=p.price_paise,
        stock=p.stock if owner else min(p.stock, 99),
        in_stock=p.stock > 0,
        media=[assets[uuid.UUID(m)] for m in p.media if uuid.UUID(m) in assets],
        active=p.active,
    )


async def add_product(db: AsyncSession, user: User, business_id: uuid.UUID, data: ProductIn) -> ProductOut:
    b = await business.owned(db, business_id, user)
    assets = await media.ready_assets(db, user.id, data.media_ids)
    p = Product(business_id=b.id, **data.model_dump(exclude={"media_ids"}), media=[str(a.id) for a in assets])
    db.add(p)
    await db.commit()
    return await _product_out(db, p, owner=True)


async def update_product(db: AsyncSession, user: User, product_id: uuid.UUID, data: ProductIn) -> ProductOut:
    p = await db.get(Product, product_id)
    if p is None:
        raise NotFound("product_not_found", "Product not found.")
    await business.owned(db, p.business_id, user)
    assets = await media.ready_assets(db, user.id, data.media_ids)
    for k, v in data.model_dump(exclude={"media_ids"}).items():
        setattr(p, k, v)
    p.media = [str(a.id) for a in assets]
    await db.commit()
    return await _product_out(db, p, owner=True)


async def catalog(db: AsyncSession, business_id: uuid.UUID, viewer: User | None) -> list[ProductOut]:
    b = await business.get_active_business(db, business_id)
    owner = viewer is not None and viewer.id == b.owner_id
    stmt = select(Product).where(Product.business_id == b.id)
    if not owner:
        stmt = stmt.where(Product.active.is_(True))
    rows = (await db.scalars(stmt.order_by(Product.created_at))).all()
    return [await _product_out(db, p, owner=owner) for p in rows]


async def _order_out(db: AsyncSession, o: Order, *, show_address: bool) -> OrderOut:
    items = (await db.scalars(select(OrderItem).where(OrderItem.order_id == o.id))).all()
    return OrderOut(
        id=o.id,
        business_id=o.business_id,
        customer_id=o.customer_id,
        status=o.status,
        payment_status=o.payment_status,
        total_paise=o.total_paise,
        fulfilment=o.fulfilment,
        wanted_on=o.wanted_on,
        note=o.note,
        items=[OrderItemOut(product_id=i.product_id, name=i.name, unit_price_paise=i.unit_price_paise, qty=i.qty) for i in items],
        created_at=o.created_at,
        address=crypto.decrypt(o.address_enc) if show_address else None,
    )


async def place_order(db: AsyncSession, customer: User, data: OrderCreate, idempotency_key: str) -> tuple[OrderOut, bool]:
    existing = await db.scalar(select(Order).where(Order.customer_id == customer.id, Order.idempotency_key == idempotency_key))
    if existing:
        return await _order_out(db, existing, show_address=True), False
    await rate_limit.enforce("order_create", str(customer.id), limit=20, window_s=3600)
    b = await business.get_active_business(db, data.business_id)
    if b.owner_id == customer.id:
        raise Forbidden("own_business", "You cannot order from your own shop.")
    if data.fulfilment == "delivery" and not (data.address and data.address.strip()):
        raise AppError("address_required", "Add a delivery address.")
    if data.wanted_on and (
        data.wanted_on < datetime.now(UTC).date() or data.wanted_on > datetime.now(UTC).date() + timedelta(days=180)
    ):
        raise AppError("invalid_date", "Choose a date within the next 6 months.")
    lines: dict[uuid.UUID, int] = {}
    for line in data.items:
        lines[line.product_id] = lines.get(line.product_id, 0) + line.qty
    order = Order(
        id=uuid7(),
        business_id=b.id,
        customer_id=customer.id,
        total_paise=0,
        fulfilment=data.fulfilment,
        address_enc=crypto.encrypt(data.address.strip()) if data.address else None,
        wanted_on=data.wanted_on,
        note=data.note,
        idempotency_key=idempotency_key,
    )
    db.add(order)
    total = 0
    biz_id = b.id
    # Lock rows in a fixed order to avoid deadlocks between concurrent multi-item orders.
    for pid in sorted(lines):
        qty = lines[pid]
        row = (
            await db.execute(
                update(Product)
                .where(Product.id == pid, Product.business_id == b.id, Product.active.is_(True), Product.stock >= qty)
                .values(stock=Product.stock - qty)
                .returning(Product.name, Product.price_paise)
            )
        ).first()
        if row is None:
            await db.rollback()
            info = (
                await db.execute(
                    select(Product.name, Product.stock, Product.business_id, Product.active).where(Product.id == pid)
                )
            ).first()
            if info is None or info.business_id != biz_id or not info.active:
                raise NotFound("product_not_found", "A product in your order was not found.")
            raise Conflict(
                "out_of_stock",
                f"Only {info.stock} left of {info.name}.",
                details={"product_id": str(pid), "available": info.stock},
            )
        db.add(OrderItem(order_id=order.id, product_id=pid, name=row.name, unit_price_paise=row.price_paise, qty=qty))
        total += row.price_paise * qty
    order.total_paise = total
    db.add(OrderStatusHistory(order_id=order.id, from_status=None, to_status="placed", actor_id=customer.id))
    emit(
        db,
        "shop.order_placed",
        {
            "order_id": str(order.id),
            "business_id": str(b.id),
            "business_owner_id": str(b.owner_id),
            "customer_id": str(customer.id),
            "total_paise": total,
        },
    )
    await db.commit()
    return await _order_out(db, order, show_address=True), True


async def _restock(db: AsyncSession, order_id: uuid.UUID) -> None:
    for item in (await db.scalars(select(OrderItem).where(OrderItem.order_id == order_id))).all():
        await db.execute(update(Product).where(Product.id == item.product_id).values(stock=Product.stock + item.qty))


async def set_status(db: AsyncSession, actor: User, order_id: uuid.UUID, to: str) -> OrderOut:
    o = await db.get(Order, order_id, with_for_update=True)
    if o is None:
        raise NotFound("order_not_found", "Order not found.")
    b = await business.get_active_business(db, o.business_id)
    if actor.id == b.owner_id:
        if to not in SELLER_FLOW.get(o.status, set()):
            raise Conflict("invalid_transition", f"A {o.status} order cannot be marked {to}.")
    elif actor.id == o.customer_id:
        if to != "cancelled" or o.status not in CUSTOMER_CANCELLABLE:
            raise Conflict("invalid_transition", "You can cancel only before the shop confirms.")
    else:
        raise NotFound("order_not_found", "Order not found.")
    if to == "cancelled":
        await _restock(db, o.id)
    db.add(OrderStatusHistory(order_id=o.id, from_status=o.status, to_status=to, actor_id=actor.id))
    old, o.status, o.updated_at = o.status, to, datetime.now(UTC)
    emit(
        db,
        "shop.order_status_changed",
        {
            "order_id": str(o.id),
            "business_owner_id": str(b.owner_id),
            "customer_id": str(o.customer_id),
            "from": old,
            "status": to,
            "by": "business" if actor.id == b.owner_id else "customer",
        },
    )
    await db.commit()
    return await _order_out(db, o, show_address=True)


async def my_orders(db: AsyncSession, customer: User) -> list[OrderOut]:
    rows = (
        await db.scalars(select(Order).where(Order.customer_id == customer.id).order_by(Order.created_at.desc()).limit(50))
    ).all()
    return [await _order_out(db, o, show_address=True) for o in rows]


async def shop_orders(db: AsyncSession, owner: User, business_id: uuid.UUID, status: str | None) -> list[OrderOut]:
    b = await business.owned(db, business_id, owner)
    stmt = select(Order).where(Order.business_id == b.id)
    if status:
        stmt = stmt.where(Order.status == status)
    rows = (await db.scalars(stmt.order_by(Order.wanted_on.asc().nulls_last(), Order.created_at.desc()).limit(100))).all()
    return [await _order_out(db, o, show_address=True) for o in rows]


# --- Interface for payments (Phase 6) ---


async def order_for_payment(db: AsyncSession, customer_id: uuid.UUID, order_id: uuid.UUID) -> Order:
    o = await db.get(Order, order_id)
    if o is None or o.customer_id != customer_id:
        raise NotFound("order_not_found", "Order not found.")
    if o.status == "cancelled" or o.payment_status == "paid":
        raise Conflict("order_not_payable", "This order cannot be paid.")
    return o


async def mark_paid(db: AsyncSession, order_id: uuid.UUID) -> None:
    await db.execute(update(Order).where(Order.id == order_id).values(payment_status="paid", updated_at=func.now()))
