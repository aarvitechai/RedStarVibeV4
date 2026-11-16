import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel

from app.api.deps import DB, CurrentUser, optional_user, require_permission
from app.modules.accounts.models import User
from app.modules.shop import service
from app.modules.shop.service import OrderCreate, OrderOut, OrderStatus, ProductIn, ProductOut

router = APIRouter(tags=["shop"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=80)]
Manager = Annotated[User, Depends(require_permission("shop:manage"))]


class StatusIn(BaseModel):
    status: OrderStatus


@router.get("/businesses/{business_id}/products", response_model=list[ProductOut])
async def catalog(business_id: uuid.UUID, request: Request, db: DB) -> list[ProductOut]:
    return await service.catalog(db, business_id, await optional_user(request, db))


@router.post("/businesses/{business_id}/products", response_model=ProductOut, status_code=201)
async def add_product(business_id: uuid.UUID, body: ProductIn, db: DB, user: Manager) -> ProductOut:
    return await service.add_product(db, user, business_id, body)


@router.put("/products/{product_id}", response_model=ProductOut)
async def update_product(product_id: uuid.UUID, body: ProductIn, db: DB, user: Manager) -> ProductOut:
    return await service.update_product(db, user, product_id, body)


@router.post("/orders", response_model=OrderOut, status_code=201, responses={200: {"model": OrderOut, "description": "Replay"}})
async def place_order(
    body: OrderCreate,
    response: Response,
    db: DB,
    key: IdempotencyKey,
    user: Annotated[User, Depends(require_permission("order:create"))],
) -> OrderOut:
    order, created = await service.place_order(db, user, body, key)
    if not created:
        response.status_code = 200
    return order


@router.get("/orders/mine", response_model=list[OrderOut])
async def my_orders(db: DB, user: CurrentUser) -> list[OrderOut]:
    return await service.my_orders(db, user)


@router.get("/businesses/{business_id}/orders", response_model=list[OrderOut])
async def shop_orders(
    business_id: uuid.UUID,
    db: DB,
    user: Manager,
    status: Annotated[str | None, Query(pattern="^(placed|confirmed|ready|shipped|delivered|cancelled)$")] = None,
) -> list[OrderOut]:
    return await service.shop_orders(db, user, business_id, status)


@router.post("/orders/{order_id}/status", response_model=OrderOut)
async def set_status(order_id: uuid.UUID, body: StatusIn, db: DB, user: CurrentUser) -> OrderOut:
    return await service.set_status(db, user, order_id, body.status)
