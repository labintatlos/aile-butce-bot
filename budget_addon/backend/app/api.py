"""HTTP arayüzü.

Route'lar iş kuralı içermez: girdiyi doğrular, `services` katmanını çağırır,
sonucu biçimlendirir. Web sitesi ve Home Assistant paneli aynı servisleri
çağırdığı için iki giriş arasında hesaplama farkı oluşamaz.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import expenses_api, incomes_api, reports_api, savings_api, settings_api
from .config import Settings, get_settings
from .database import get_session
from .models.category import Category
from .models.payment_method import DEFAULT_CURRENCY, PaymentMethod
from .models.user import User
from .schemas import (
    BootstrapOut,
    CategoryOut,
    PaymentMethodOut,
    UserOut,
)
from .security.identity import current_user
from .utils.time import local_today

router = APIRouter(prefix="/api")


@router.get("/bootstrap", response_model=BootstrapOut)
async def bootstrap(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> BootstrapOut:
    """Arayüzün açılışta ihtiyaç duyduğu her şey tek istekte."""
    categories = (
        await session.scalars(
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name)
        )
    ).all()
    methods = (
        await session.scalars(
            select(PaymentMethod)
            .where(PaymentMethod.is_active.is_(True))
            .order_by(PaymentMethod.type, PaymentMethod.name)
        )
    ).all()
    people = (
        await session.scalars(
            select(User).where(User.is_active.is_(True)).order_by(User.id)
        )
    ).all()
    return BootstrapOut(
        user=UserOut.model_validate(user),
        categories=[CategoryOut.model_validate(c) for c in categories],
        payment_methods=[PaymentMethodOut.model_validate(m) for m in methods],
        people=[UserOut.model_validate(p) for p in people],
        today=local_today(settings.timezone),
        currency=DEFAULT_CURRENCY,
    )


# Konu bazli router'lar; hepsi `/api` altinda yayimlanir.
for _sub in (expenses_api, reports_api, settings_api, incomes_api, savings_api):
    router.include_router(_sub.router)
