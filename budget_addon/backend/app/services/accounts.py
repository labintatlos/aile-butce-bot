"""Hesaplar, bakiyeler, transferler ve net varlık.

Bakiye hesabı (bkz. `models/account.py`): bir tarihteki bakiye, o tarihe
kadarki son `balance` kaydı ile ondan sonraki transfer ve düzeltmelerin
toplamıdır. Hiç bakiye kaydı yoksa yalnızca hareketler toplanır.

**Net varlık** = hesap bakiyelerinin toplamı − kart borcu. Kart borcu
taksitlerden hesaplanır: o tarihte yapılmış ve son ödeme günü henüz gelmemiş
taksitler borçtur; aynı karta düşen ve henüz son ödemesi gelmemiş iade
alacakları borçtan düşülür. Birikim hedefleri ayrıca eklenmez: hedefe
ayrılan para zaten bir hesapta durur.
"""

from __future__ import annotations

import secrets
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.account import (
    ACCOUNT_KINDS,
    ENTRY_ADJUSTMENT,
    ENTRY_BALANCE,
    ENTRY_TRANSFER,
    Account,
    AccountEntry,
)
from ..models.audit_log import ACTION_CREATE, ACTION_DELETE, ACTION_UPDATE
from ..models.expense import Expense
from ..models.installment import STATUS_SCHEDULED, ExpenseInstallment
from ..models.payment_method import TYPE_CREDIT_CARD, PaymentMethod
from ..models.refund import Refund
from ..models.user import User
from ..utils.time import month_bounds
from .audit import record_audit
from .finance.dates import MONTHS_PER_YEAR

ENTITY_ACCOUNT = "account"
ENTITY_ACCOUNT_ENTRY = "account_entry"
ACCOUNT_FIELDS = frozenset({"name", "kind", "sort_order", "is_active", "notes"})
HISTORY_MONTHS = 12
MAX_ENTRIES = 200


class AccountError(Exception):
    """Kullanıcıya gösterilebilir, iş kuralı kaynaklı hata."""


# ---------------------------------------------------------------------------
# Bakiye hesabı
# ---------------------------------------------------------------------------


def balance_at(entries: list[AccountEntry], when: date) -> int:
    """Bir hesabın `when` günü sonundaki bakiyesi.

    `entries` yalnızca o hesabın kayıtlarıdır; sıralı gelmeleri gerekmez.
    """
    relevant = sorted(
        (entry for entry in entries if entry.entry_date <= when),
        key=lambda entry: (entry.entry_date, entry.id),
    )
    balance = 0
    for entry in relevant:
        if entry.kind == ENTRY_BALANCE:
            balance = entry.amount_minor
        else:
            balance += entry.amount_minor
    return balance


async def _entries_by_account(session: AsyncSession) -> dict[int, list[AccountEntry]]:
    grouped: dict[int, list[AccountEntry]] = defaultdict(list)
    for entry in (await session.scalars(select(AccountEntry))).all():
        grouped[entry.account_id].append(entry)
    return grouped


async def card_debt_at(session: AsyncSession, when: date) -> int:
    """Kart borcunun `when` günündeki tutarı (iade alacakları düşülmüş)."""
    installments = int(
        await session.scalar(
            select(func.coalesce(func.sum(ExpenseInstallment.amount_minor), 0))
            .join(Expense, ExpenseInstallment.expense_id == Expense.id)
            .where(
                Expense.deleted_at.is_(None),
                Expense.payment_method_type_snapshot == TYPE_CREDIT_CARD,
                Expense.transaction_date <= when,
                ExpenseInstallment.status == STATUS_SCHEDULED,
                ExpenseInstallment.due_date >= when,
            )
        )
        or 0
    )
    credits = int(
        await session.scalar(
            select(func.coalesce(func.sum(Refund.amount_minor), 0))
            .join(Expense, Refund.expense_id == Expense.id)
            .where(
                Expense.deleted_at.is_(None),
                Refund.deleted_at.is_(None),
                Refund.refund_date <= when,
                Refund.due_date.is_not(None),
                Refund.due_date >= when,
            )
        )
        or 0
    )
    return max(installments - credits, 0)


@dataclass(frozen=True, slots=True)
class AccountBalance:
    account: Account
    balance_minor: int
    last_balance_date: date | None
    """En son bakiye güncellemesinin tarihi; hiç girilmemişse boş."""


@dataclass(frozen=True, slots=True)
class NetWorthPoint:
    when: date
    assets_minor: int
    card_debt_minor: int

    @property
    def net_minor(self) -> int:
        return self.assets_minor - self.card_debt_minor


@dataclass(frozen=True, slots=True)
class Overview:
    accounts: list[AccountBalance]
    today: NetWorthPoint
    history: list[NetWorthPoint]


def _month_ends(today: date, months: int) -> list[date]:
    current = today.year * MONTHS_PER_YEAR + (today.month - 1)
    ends = []
    for index in range(current - months, current):
        year, month_index = divmod(index, MONTHS_PER_YEAR)
        ends.append(month_bounds(year, month_index + 1)[1])
    return ends


async def overview(
    session: AsyncSession, *, today: date, months: int = HISTORY_MONTHS
) -> Overview:
    """Hesap bakiyeleri, bugünkü net varlık ve son ayların ay sonu net varlığı."""
    accounts = (
        await session.scalars(select(Account).order_by(Account.sort_order, Account.name))
    ).all()
    entries = await _entries_by_account(session)

    balances = []
    for account in accounts:
        own = entries.get(account.id, [])
        snapshots = [entry.entry_date for entry in own if entry.kind == ENTRY_BALANCE]
        balances.append(
            AccountBalance(
                account=account,
                balance_minor=balance_at(own, today),
                last_balance_date=max(snapshots) if snapshots else None,
            )
        )

    def assets(when: date) -> int:
        return sum(
            balance_at(entries.get(account.id, []), when)
            for account in accounts
            if account.is_active
        )

    history = [
        NetWorthPoint(when=when, assets_minor=assets(when), card_debt_minor=await card_debt_at(session, when))
        for when in _month_ends(today, months)
    ]
    now = NetWorthPoint(
        when=today, assets_minor=assets(today), card_debt_minor=await card_debt_at(session, today)
    )
    return Overview(accounts=balances, today=now, history=history)


# ---------------------------------------------------------------------------
# Hesap yönetimi
# ---------------------------------------------------------------------------


def _clean_name(name: str) -> str:
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise AccountError("Hesaba bir ad verin")
    return cleaned[:64]


async def get_account(session: AsyncSession, account_id: int) -> Account:
    account = await session.get(Account, account_id)
    if account is None:
        raise AccountError("Hesap bulunamadı")
    return account


async def create_account(
    session: AsyncSession,
    *,
    user: User,
    name: str,
    kind: str,
    opening_balance_minor: int | None,
    opening_date: date,
    notes: str | None = None,
) -> Account:
    """Hesabı açar; başlangıç bakiyesi verildiyse ilk bakiye kaydını da yazar."""
    if kind not in ACCOUNT_KINDS:
        raise AccountError("Geçersiz hesap türü")
    clean = _clean_name(name)
    if await session.scalar(select(Account.id).where(Account.name == clean)):
        raise AccountError(f"'{clean}' adında bir hesap zaten var")
    account = Account(name=clean, kind=kind, notes=(notes or "").strip() or None)
    session.add(account)
    await session.flush()
    if opening_balance_minor is not None:
        session.add(
            AccountEntry(
                account_id=account.id,
                entry_date=opening_date,
                kind=ENTRY_BALANCE,
                amount_minor=opening_balance_minor,
                created_by_user_id=user.id,
                note="Açılış bakiyesi",
            )
        )
    record_audit(
        session,
        user_id=user.id,
        entity_type=ENTITY_ACCOUNT,
        entity_id=account.id,
        action=ACTION_CREATE,
        new_data={"name": clean, "kind": kind, "opening_balance_minor": opening_balance_minor},
    )
    await session.commit()
    return account


async def update_account(
    session: AsyncSession, *, user: User, account: Account, changes: dict
) -> Account:
    unknown = set(changes) - ACCOUNT_FIELDS
    if unknown:
        raise AccountError(f"Düzenlenemeyen alan: {', '.join(sorted(unknown))}")
    if "kind" in changes and changes["kind"] not in ACCOUNT_KINDS:
        raise AccountError("Geçersiz hesap türü")
    if "name" in changes:
        changes["name"] = _clean_name(changes["name"])
        clash = await session.scalar(
            select(Account.id).where(Account.name == changes["name"], Account.id != account.id)
        )
        if clash:
            raise AccountError(f"'{changes['name']}' adında bir hesap zaten var")
    before = {"name": account.name, "kind": account.kind, "is_active": account.is_active}
    for key, value in changes.items():
        setattr(account, key, value)
    record_audit(
        session,
        user_id=user.id,
        entity_type=ENTITY_ACCOUNT,
        entity_id=account.id,
        action=ACTION_UPDATE,
        old_data=before,
        new_data={"name": account.name, "kind": account.kind, "is_active": account.is_active},
    )
    await session.commit()
    return account


async def delete_account(session: AsyncSession, *, user: User, account: Account) -> None:
    """Hesabı ve hareketlerini siler. Transferin karşı ayağı da birlikte gider.

    Karşı ayağı bırakmak, öbür hesabın bakiyesini nedensiz yere değiştirirdi.
    """
    groups = (
        await session.scalars(
            select(AccountEntry.transfer_group).where(
                AccountEntry.account_id == account.id,
                AccountEntry.transfer_group.is_not(None),
            )
        )
    ).all()
    if groups:
        await session.execute(delete(AccountEntry).where(AccountEntry.transfer_group.in_(groups)))
    await session.execute(delete(AccountEntry).where(AccountEntry.account_id == account.id))
    record_audit(
        session,
        user_id=user.id,
        entity_type=ENTITY_ACCOUNT,
        entity_id=account.id,
        action=ACTION_DELETE,
        old_data={"name": account.name, "kind": account.kind},
    )
    await session.delete(account)
    await session.commit()


# ---------------------------------------------------------------------------
# Hareketler
# ---------------------------------------------------------------------------


async def list_entries(session: AsyncSession, account_id: int) -> list[AccountEntry]:
    await get_account(session, account_id)
    return list(
        (
            await session.scalars(
                select(AccountEntry)
                .where(AccountEntry.account_id == account_id)
                .order_by(AccountEntry.entry_date.desc(), AccountEntry.id.desc())
                .limit(MAX_ENTRIES)
            )
        ).all()
    )


def _audit_entry(session: AsyncSession, user: User, entry: AccountEntry, action: str) -> None:
    payload = {
        "account_id": entry.account_id,
        "entry_date": entry.entry_date,
        "kind": entry.kind,
        "amount_minor": entry.amount_minor,
        "transfer_group": entry.transfer_group,
    }
    record_audit(
        session,
        user_id=user.id,
        entity_type=ENTITY_ACCOUNT_ENTRY,
        entity_id=entry.id,
        action=action,
        new_data=payload if action == ACTION_CREATE else None,
        old_data=payload if action == ACTION_DELETE else None,
    )


async def record_balance(
    session: AsyncSession,
    *,
    user: User,
    account_id: int,
    balance_minor: int,
    when: date,
    note: str | None = None,
) -> AccountEntry:
    """Hesabın o günkü bakiyesini yazar. Eksi bakiye (ek hesap) kabul edilir."""
    await get_account(session, account_id)
    entry = AccountEntry(
        account_id=account_id,
        entry_date=when,
        kind=ENTRY_BALANCE,
        amount_minor=balance_minor,
        note=(note or "").strip() or None,
        created_by_user_id=user.id,
    )
    session.add(entry)
    await session.flush()
    _audit_entry(session, user, entry, ACTION_CREATE)
    await session.commit()
    return entry


async def record_adjustment(
    session: AsyncSession,
    *,
    user: User,
    account_id: int,
    amount_minor: int,
    when: date,
    note: str | None = None,
) -> AccountEntry:
    """Faiz, masraf gibi işaretli bir fark yazar."""
    await get_account(session, account_id)
    if amount_minor == 0:
        raise AccountError("Tutar sıfır olamaz")
    entry = AccountEntry(
        account_id=account_id,
        entry_date=when,
        kind=ENTRY_ADJUSTMENT,
        amount_minor=amount_minor,
        note=(note or "").strip() or None,
        created_by_user_id=user.id,
    )
    session.add(entry)
    await session.flush()
    _audit_entry(session, user, entry, ACTION_CREATE)
    await session.commit()
    return entry


async def transfer(
    session: AsyncSession,
    *,
    user: User,
    from_account_id: int,
    to_account_id: int | None,
    payment_method_id: int | None,
    amount_minor: int,
    when: date,
    note: str | None = None,
) -> list[AccountEntry]:
    """Hesaplar arası aktarım veya bir hesaptan kart ödemesi.

    Hesaplar arası aktarımda iki ayak yazılır ve aynı `transfer_group` ile
    bağlanır. Kart ödemesinde yalnızca ödeyen hesabın ayağı yazılır: kart
    borcu taksitlerden hesaplandığı için ayrıca düşülmez.

    Hiçbiri harcama ya da gelir değildir.
    """
    if amount_minor <= 0:
        raise AccountError("Tutar sıfırdan büyük olmalıdır")
    await get_account(session, from_account_id)
    if (to_account_id is None) == (payment_method_id is None):
        raise AccountError("Paranın gideceği hesabı veya ödenen kartı seçin")
    if to_account_id is not None:
        if to_account_id == from_account_id:
            raise AccountError("Bir hesaptan kendisine aktarım yapılamaz")
        await get_account(session, to_account_id)
    card_name = None
    if payment_method_id is not None:
        card = await session.get(PaymentMethod, payment_method_id)
        if card is None or card.type != TYPE_CREDIT_CARD:
            raise AccountError("Kredi kartı bulunamadı")
        card_name = card.name

    group = secrets.token_hex(8)
    clean_note = (note or "").strip() or None
    legs = [
        AccountEntry(
            account_id=from_account_id,
            entry_date=when,
            kind=ENTRY_TRANSFER,
            amount_minor=-amount_minor,
            transfer_group=group,
            payment_method_id=payment_method_id,
            note=clean_note or (f"Kart ödemesi: {card_name}" if card_name else None),
            created_by_user_id=user.id,
        )
    ]
    if to_account_id is not None:
        legs.append(
            AccountEntry(
                account_id=to_account_id,
                entry_date=when,
                kind=ENTRY_TRANSFER,
                amount_minor=amount_minor,
                transfer_group=group,
                note=clean_note,
                created_by_user_id=user.id,
            )
        )
    session.add_all(legs)
    await session.flush()
    for leg in legs:
        _audit_entry(session, user, leg, ACTION_CREATE)
    await session.commit()
    return legs


async def delete_entry(session: AsyncSession, *, user: User, entry_id: int) -> None:
    """Hareketi siler; transfer ise iki ayağı birlikte silinir."""
    entry = await session.get(AccountEntry, entry_id)
    if entry is None:
        raise AccountError("Hareket bulunamadı")
    targets = [entry]
    if entry.transfer_group:
        targets = list(
            (
                await session.scalars(
                    select(AccountEntry).where(AccountEntry.transfer_group == entry.transfer_group)
                )
            ).all()
        )
    for target in targets:
        _audit_entry(session, user, target, ACTION_DELETE)
        await session.delete(target)
    await session.commit()
