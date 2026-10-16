"""Hesap, bakiye, transfer ve net varlık uç noktaları.

Route'lar iş kuralı içermez: girdiyi doğrular, `services` katmanını
çağırır, sonucu biçimlendirir.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_session
from .models.user import User
from .schemas import (
    AccountCreateIn,
    AccountEntryOut,
    AccountOut,
    AccountsOverviewOut,
    AccountUpdateIn,
    AdjustmentIn,
    BalanceIn,
    Money,
    NetWorthPointOut,
    TransferIn,
)
from .security.identity import current_user
from .services import accounts
from .utils.time import local_today

router = APIRouter()

UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_ENTITY


def _point(point: accounts.NetWorthPoint) -> NetWorthPointOut:
    return NetWorthPointOut(
        when=point.when,
        assets=Money.of(point.assets_minor),
        card_debt=Money.of(point.card_debt_minor),
        net=Money.of(point.net_minor),
    )


def _entry_out(entry) -> AccountEntryOut:
    return AccountEntryOut(
        id=entry.id,
        account_id=entry.account_id,
        entry_date=entry.entry_date,
        kind=entry.kind,
        amount=Money.of(entry.amount_minor),
        transfer_group=entry.transfer_group,
        payment_method_id=entry.payment_method_id,
        note=entry.note,
    )


@router.get("/accounts", response_model=AccountsOverviewOut)
async def read_accounts(
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AccountsOverviewOut:
    """Hesap bakiyeleri, bugünkü net varlık ve son on iki ayın ay sonları."""
    result = await accounts.overview(session, today=local_today(settings.timezone))
    return AccountsOverviewOut(
        accounts=[
            AccountOut(
                id=item.account.id,
                name=item.account.name,
                kind=item.account.kind,
                is_active=item.account.is_active,
                notes=item.account.notes,
                balance=Money.of(item.balance_minor),
                last_balance_date=item.last_balance_date,
            )
            for item in result.accounts
        ],
        today=_point(result.today),
        history=[_point(point) for point in result.history],
    )


@router.post(
    "/accounts", response_model=AccountsOverviewOut, status_code=status.HTTP_201_CREATED
)
async def add_account(
    payload: AccountCreateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AccountsOverviewOut:
    try:
        await accounts.create_account(
            session,
            user=user,
            name=payload.name,
            kind=payload.kind,
            opening_balance_minor=payload.opening_balance_minor,
            opening_date=payload.opening_date or local_today(settings.timezone),
            notes=payload.notes,
        )
    except accounts.AccountError as exc:
        await session.rollback()
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    return await read_accounts(_user=user, session=session, settings=settings)


@router.patch("/accounts/{account_id}", response_model=AccountsOverviewOut)
async def edit_account(
    account_id: int,
    payload: AccountUpdateIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AccountsOverviewOut:
    try:
        account = await accounts.get_account(session, account_id)
        await accounts.update_account(
            session,
            user=user,
            account=account,
            changes=payload.model_dump(exclude_unset=True, exclude_none=True),
        )
    except accounts.AccountError as exc:
        await session.rollback()
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    return await read_accounts(_user=user, session=session, settings=settings)


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_account(
    account_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        account = await accounts.get_account(session, account_id)
    except accounts.AccountError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    await accounts.delete_account(session, user=user, account=account)


@router.get("/accounts/{account_id}/entries", response_model=list[AccountEntryOut])
async def read_entries(
    account_id: int,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AccountEntryOut]:
    try:
        entries = await accounts.list_entries(session, account_id)
    except accounts.AccountError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return [_entry_out(entry) for entry in entries]


@router.post("/accounts/{account_id}/balance", response_model=AccountEntryOut)
async def add_balance(
    account_id: int,
    payload: BalanceIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AccountEntryOut:
    """Hesabın o günkü bakiyesini yazar."""
    try:
        entry = await accounts.record_balance(
            session,
            user=user,
            account_id=account_id,
            balance_minor=payload.balance_minor,
            when=payload.entry_date or local_today(settings.timezone),
            note=payload.note,
        )
    except accounts.AccountError as exc:
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    return _entry_out(entry)


@router.post("/accounts/{account_id}/adjustments", response_model=AccountEntryOut)
async def add_adjustment(
    account_id: int,
    payload: AdjustmentIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AccountEntryOut:
    """Faiz, masraf gibi işaretli bir fark yazar."""
    try:
        entry = await accounts.record_adjustment(
            session,
            user=user,
            account_id=account_id,
            amount_minor=payload.amount_minor,
            when=payload.entry_date or local_today(settings.timezone),
            note=payload.note,
        )
    except accounts.AccountError as exc:
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    return _entry_out(entry)


@router.post("/transfers", response_model=list[AccountEntryOut])
async def add_transfer(
    payload: TransferIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[AccountEntryOut]:
    """Hesaplar arası aktarım veya kart ödemesi. Harcama ya da gelir değildir."""
    try:
        legs = await accounts.transfer(
            session,
            user=user,
            from_account_id=payload.from_account_id,
            to_account_id=payload.to_account_id,
            payment_method_id=payload.payment_method_id,
            amount_minor=payload.amount_minor,
            when=payload.entry_date or local_today(settings.timezone),
            note=payload.note,
        )
    except accounts.AccountError as exc:
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    return [_entry_out(leg) for leg in legs]


@router.delete("/account-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_entry(
    entry_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Hareketi siler; transferin iki ayağı birlikte silinir."""
    try:
        await accounts.delete_entry(session, user=user, entry_id=entry_id)
    except accounts.AccountError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
