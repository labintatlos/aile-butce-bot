"""Ödeme yöntemi, kategori, sabit gider ve kişisel bütçe ayarları.

Route'lar iş kuralı içermez: girdiyi doğrular, `services` katmanını
çağırır, sonucu biçimlendirir.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_session
from .models.category import Category
from .models.payment_method import PaymentMethod
from .models.user import User
from .reports_api import personal_budget_report
from .schemas import (
    CategoryCreateIn,
    CategoryOut,
    CategorySuggestionOut,
    CategoryUpdateIn,
    Money,
    PaymentMethodCreateIn,
    PaymentMethodOut,
    PaymentMethodUpdateIn,
    PersonalBudgetIn,
    PersonalBudgetOut,
    RecurringExpenseCreateIn,
    RecurringExpenseOut,
    RecurringExpenseUpdateIn,
)
from .security.identity import current_user
from .services import (
    personal_budgets,
    recurring,
    settings_service,
)
from .services.category_suggest import suggest_category
from .services.finance.money import parse_amount_to_minor

router = APIRouter()


@router.get("/payment-methods", response_model=list[PaymentMethodOut])
async def read_payment_methods(
    include_inactive: bool = False,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[PaymentMethodOut]:
    methods = await settings_service.list_payment_methods(
        session, include_inactive=include_inactive
    )
    return [PaymentMethodOut.model_validate(m) for m in methods]


@router.post(
    "/payment-methods", response_model=PaymentMethodOut, status_code=status.HTTP_201_CREATED
)
async def add_payment_method(
    payload: PaymentMethodCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PaymentMethodOut:
    try:
        method = await settings_service.create_payment_method(
            session, user=user, **payload.model_dump()
        )
    except settings_service.SettingsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return PaymentMethodOut.model_validate(method)


@router.patch("/payment-methods/{method_id}", response_model=PaymentMethodOut)
async def edit_payment_method(
    method_id: int,
    payload: PaymentMethodUpdateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PaymentMethodOut:
    """Kart ayarlarını düzeltir. Geçmiş taksit planları değişmez."""
    method = await session.get(PaymentMethod, method_id)
    if method is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ödeme yöntemi bulunamadı")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return PaymentMethodOut.model_validate(method)
    try:
        await settings_service.update_payment_method(
            session, user=user, method=method, changes=changes
        )
    except settings_service.SettingsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return PaymentMethodOut.model_validate(method)


@router.get("/categories", response_model=list[CategoryOut])
async def read_categories(
    include_inactive: bool = False,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CategoryOut]:
    categories = await settings_service.list_categories(
        session, include_inactive=include_inactive
    )
    return [CategoryOut.model_validate(c) for c in categories]


@router.get("/categories/suggest", response_model=CategorySuggestionOut)
async def suggest_category_for(
    description: str = Query("", max_length=200),
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> CategorySuggestionOut:
    """Açıklamaya göre geçmiş kayıtlardan kategori önerir. Hiçbir şey kaydetmez."""
    category = await suggest_category(session, description)
    return CategorySuggestionOut(category_id=category.id if category else None)


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def add_category(
    payload: CategoryCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> CategoryOut:
    try:
        category = await settings_service.create_category(
            session, user=user, **payload.model_dump()
        )
    except settings_service.SettingsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return CategoryOut.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def edit_category(
    category_id: int,
    payload: CategoryUpdateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> CategoryOut:
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kategori bulunamadı")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if changes.get("monthly_budget_minor") == 0:
        # Sifir "hedefi kaldir" demektir: exclude_none bir null govdeyi zaten
        # eliyor, dolayisiyla silme niyetini tasiyacak baska bir deger yok.
        changes["monthly_budget_minor"] = None
    if not changes:
        return CategoryOut.model_validate(category)
    try:
        await settings_service.update_category(
            session, user=user, category=category, changes=changes
        )
    except settings_service.SettingsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return CategoryOut.model_validate(category)


@router.delete("/payment-methods/{method_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_payment_method(
    method_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Kullanılmayan bir ödeme yöntemini siler.

    Harcamalarda kullanılıyorsa `409` döner; çağıran tarafın onu pasife alması
    beklenir. Silmek, geçmiş harcamaların ödeme yöntemini okunamaz hâle
    getirirdi.
    """
    method = await session.get(PaymentMethod, method_id)
    if method is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ödeme yöntemi bulunamadı")
    try:
        await settings_service.delete_payment_method(session, user=user, method=method)
    except settings_service.SettingsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_category(
    category_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Kullanılmayan bir kategoriyi siler; kullanılıyorsa `409` döner."""
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kategori bulunamadı")
    try:
        await settings_service.delete_category(session, user=user, category=category)
    except settings_service.SettingsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


def _recurring_out(template) -> RecurringExpenseOut:
    return RecurringExpenseOut(
        id=template.id,
        name=template.name,
        category_id=template.category_id,
        payment_method_id=template.payment_method_id,
        amount=Money.of(template.amount_minor),
        day_of_month=template.day_of_month,
        start_date=template.start_date,
        notes=template.notes,
        is_active=template.is_active,
    )


@router.get("/recurring", response_model=list[RecurringExpenseOut])
async def read_recurring(
    include_inactive: bool = True,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[RecurringExpenseOut]:
    templates = await recurring.list_templates(
        session, include_inactive=include_inactive
    )
    return [_recurring_out(template) for template in templates]


@router.post(
    "/recurring",
    response_model=RecurringExpenseOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_recurring(
    payload: RecurringExpenseCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> RecurringExpenseOut:
    try:
        template = await recurring.create_template(
            session,
            user=user,
            name=payload.name,
            category_id=payload.category_id,
            payment_method_id=payload.payment_method_id,
            amount=payload.amount_minor,
            day_of_month=payload.day_of_month,
            start_date=payload.start_date,
            notes=payload.notes,
        )
    except (recurring.RecurringError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _recurring_out(template)


@router.patch("/recurring/{template_id}", response_model=RecurringExpenseOut)
async def edit_recurring(
    template_id: int,
    payload: RecurringExpenseUpdateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> RecurringExpenseOut:
    template = await recurring.get_template(session, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sabit gider bulunamadı")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return _recurring_out(template)
    try:
        await recurring.update_template(session, user=user, template=template, **changes)
    except (recurring.RecurringError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _recurring_out(template)


@router.delete("/recurring/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_recurring(
    template_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    template = await recurring.get_template(session, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sabit gider bulunamadı")
    await recurring.delete_template(session, user=user, template=template)


@router.put("/personal-budgets/{user_id}", response_model=list[PersonalBudgetOut])
async def set_personal_budget(
    user_id: int,
    payload: PersonalBudgetIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[PersonalBudgetOut]:
    """Bir kişinin o yılki kişisel bütçesini belirler; boş tutar kaldırır."""
    try:
        amount = (
            parse_amount_to_minor(payload.amount)
            if payload.amount and payload.amount.strip()
            else None
        )
        await personal_budgets.set_budget(
            session, user_id=user_id, year=payload.year, amount_minor=amount
        )
    except (personal_budgets.PersonalBudgetError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return await personal_budget_report(
        year=payload.year, _user=user, session=session, settings=settings
    )
