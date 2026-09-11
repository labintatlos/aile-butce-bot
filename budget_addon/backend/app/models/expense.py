"""Harcama kaydı.

Kart koşullarının anlık görüntüsü (`*_snapshot`) burada saklanır: kart ayarı
sonradan değişse bile bu harcamanın taksit planı yeniden hesaplanmaz.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .payment_method import DEFAULT_CURRENCY

PUBLIC_ID_PREFIX = "EXP"
PUBLIC_ID_DIGITS = 6


def format_public_id(expense_id: int) -> str:
    """`EXP-000184` biçiminde, kullanıcıya gösterilen kimlik üretir."""
    return f"{PUBLIC_ID_PREFIX}-{expense_id:0{PUBLIC_ID_DIGITS}d}"


class Expense(TimestampMixin, Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("total_amount_minor > 0", name="ck_expense_amount_positive"),
        CheckConstraint(
            "installment_count BETWEEN 1 AND 12", name="ck_expense_installment_range"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)

    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    payment_method_id: Mapped[int] = mapped_column(
        ForeignKey("payment_methods.id", ondelete="RESTRICT"), index=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )

    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    total_amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY)
    installment_count: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    """Harcama ortak (ev) mı, yoksa kişisel mi.

    "Ortak" burada evin ortak harcamasını, yani hanenin genel giderini ifade
    eder; iki kişi arasında bölüşülüp denkleştirilecek bir borç değildir. İki
    kişilik bir kurulumda harcamaların çoğu ortaktır; bu yüzden varsayılan
    ortaktır. Kişisel işaretlenen harcama raporlarda görünmeye devam eder ama
    ortak toplamların dışında, sahibinin kişisel bütçesinden düşer."""

    owner_user_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    """Kişisel harcamanın kime ait olduğu; ortak harcamada boştur.

    Kaydı girenden bağımsızdır: Aykut, Aslıhan'ın ayakkabısını girebilir ve
    harcama Aslıhan'ın yıllık kişisel bütçesinden düşer. `is_shared` bu alanla
    her zaman uyumlu tutulur (`is_shared == (owner_user_id is None)`).

    Yabancı anahtar `recurring_expense_id` ile aynı nedenle veritabanı
    düzeyinde tanımlanmaz."""

    receipt_file_id: Mapped[str | None] = mapped_column(
        String(256), default=None
    )
    """Fiş fotoğrafının Telegram dosya kimliği.

    Fotoğrafın kendisi saklanmaz: Telegram dosyayı zaten tutuyor ve bu kimlik
    aynı bot için kalıcıdır. Böylece eklenti disk doldurmaz ve fiş, kullanıcının
    zaten baktığı yerde, sohbetin içinde açılır.

    Tutar fotoğraftan **okunmaz**. Fiş yalnızca kanıttır; tutarı kullanıcı
    yazar, çünkü finansal hesapta tahmin yürütülmez.

    Site fişleri kendisi saklar (`receipt_path`); bu sütun yalnızca Telegram
    döneminden kalan ve henüz aktarılmamış fişler için durur."""

    receipt_path: Mapped[str | None] = mapped_column(String(64), default=None)
    """Veri dizinindeki `receipts/` klasöründe fiş fotoğrafının dosya adı."""

    recurring_expense_id: Mapped[int | None] = mapped_column(
        Integer, index=True, default=None
    )
    """Bu kaydı üreten sabit gider şablonu.

    Aynı şablonun aynı ay içinde iki kez kayıt üretmesi bu bağ üzerinden
    engellenir; kullanıcı üretilen kaydı silse bile bağ durduğu için sabit
    gider ertesi gün yeniden canlanmaz.

    Yabancı anahtar **bilinçli olarak veritabanı düzeyinde tanımlanmaz**:
    SQLite mevcut bir tabloya kısıt ekleyemez ve `expenses` tablosunu yalnızca
    bunun için yeniden oluşturmak, üzerindeki CHECK kısıtlarını riske atardı.
    Bağın boşaltılması `recurring.delete_template` içinde, silme ile aynı
    transaction'da yapılır; böylece kimliği geri dönüşen yeni bir şablon eski
    kayıtlarla karışamaz."""

    # --- Harcama anindaki kart kosullarinin anlik goruntusu ---
    payment_method_type_snapshot: Mapped[str] = mapped_column(String(16))
    payment_method_name_snapshot: Mapped[str] = mapped_column(String(64))
    statement_day_snapshot: Mapped[int | None] = mapped_column(Integer, default=None)
    due_offset_days_snapshot: Mapped[int | None] = mapped_column(Integer, default=None)
    cutoff_inclusive_snapshot: Mapped[bool | None] = mapped_column(Boolean, default=None)

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )

    # Kategori ve kullanici kucuk tablolardir; her zaman birlikte yuklenmeleri
    # asenkron oturumda beklenmedik tembel yukleme riskini ortadan kaldirir.
    category: Mapped["Category"] = relationship(lazy="selectin")
    created_by: Mapped["User"] = relationship(
        lazy="selectin", foreign_keys=[created_by_user_id]
    )
    owner: Mapped["User | None"] = relationship(
        primaryjoin="foreign(Expense.owner_user_id) == User.id",
        lazy="selectin",
        viewonly=True,
    )

    installments: Mapped[list["ExpenseInstallment"]] = relationship(
        back_populates="expense",
        cascade="all, delete-orphan",
        order_by="ExpenseInstallment.installment_number",
        # Asenkron oturumda tembel yukleme ortuk IO demektir ve MissingGreenlet
        # hatasi verir; taksitler her zaman ust kayitla birlikte yuklenir.
        lazy="selectin",
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Expense {self.public_id} {self.total_amount_minor}kr>"
