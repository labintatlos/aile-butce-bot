/**
 * Ayarlar: hesap, ödeme yöntemleri ve kategoriler.
 *
 * Kart günlerini değiştirmek yalnızca yeni harcamaları etkiler; oluşturulmuş
 * taksit planları sabit kalır (§ geçmiş yeniden hesaplanmaz).
 */

import { useState, type FormEvent } from "react";

import {
  api,
  type Category,
  type Me,
  type PaymentMethod,
  type PaymentMethodInput,
  type PaymentMethodType,
} from "../api";
import { Icon } from "../components/icons";
import {
  Card,
  ConfirmButton,
  Empty,
  ErrorNote,
  Field,
  Loading,
  Modal,
  PageHeader,
  Segmented,
  Toggle,
  useToast,
} from "../components/ui";
import { authSourceLabel, initialOf, useSession } from "../context";
import { formatMinor, minorToInput, parseAmountToMinor, sanitiseAmount } from "../format";
import { errorMessage, useAsync } from "../hooks";

const TYPE_OPTIONS: readonly { value: PaymentMethodType; label: string }[] = [
  { value: "credit_card", label: "Kredi kartı" },
  { value: "cash", label: "Nakit / banka kartı" },
];

const EMOJI_SUGGESTIONS = ["🛒", "🍽️", "🚗", "⛽", "🏠", "💡", "📱", "👕", "💊", "🎁", "✈️", "🎓", "🐾", "🎬", "📦", "💳"];

export function Settings() {
  const { me, setMe, logout, refresh, users } = useSession();
  const toast = useToast();
  const [methodEditing, setMethodEditing] = useState<PaymentMethod | "new" | null>(null);
  const [categoryEditing, setCategoryEditing] = useState<Category | "new" | null>(null);
  const [savingReminders, setSavingReminders] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);

  const state = useAsync(async () => {
    const [methods, categories, cards] = await Promise.all([
      api.paymentMethods(),
      api.categories(),
      api.cards(),
    ]);
    return { methods, categories, cards };
  }, []);

  const afterChange = (message: string) => {
    toast(message);
    state.reload();
    // Form ve filtrelerdeki listeler de guncellensin.
    refresh().catch(() => undefined);
  };

  const toggleReminders = async (enabled: boolean) => {
    setSavingReminders(true);
    try {
      setMe(await api.updateMe({ reminders_enabled: enabled }));
      toast(enabled ? "Hatırlatmalar açıldı." : "Hatırlatmalar kapatıldı.");
    } catch (cause: unknown) {
      toast(errorMessage(cause), "danger");
    } finally {
      setSavingReminders(false);
    }
  };

  const ownerName = (id: number | null) =>
    users.find((user) => user.id === id)?.display_name ?? null;

  const limits = new Map(
    (state.data?.cards ?? []).map((card) => [card.payment_method_id, card.credit_limit?.minor ?? null]),
  );

  return (
    <>
      <PageHeader title="Ayarlar" subtitle="Hesabınız, kartlarınız ve kategorileriniz" />

      {changingPassword && (
        <PasswordForm
          onClose={() => setChangingPassword(false)}
          onSaved={(updated) => {
            setChangingPassword(false);
            setMe(updated);
            toast("Şifreniz değiştirildi. Diğer cihazlardaki oturumlar kapatıldı.");
          }}
        />
      )}

      <div className="grid two">
        <div className="stack">
          <Card title="Hesap">
            <div className="row">
              <span className="avatar">{initialOf(me.display_name)}</span>
              <div className="list-main">
                <div className="strong">{me.display_name}</div>
                <div className="muted small">
                  {me.username ? `@${me.username} · ` : ""}
                  {authSourceLabel(me.auth_source)} ile giriş yapıldı
                </div>
              </div>
            </div>
            <div className="divider" />
            <Toggle
              checked={me.reminders_enabled}
              disabled={savingReminders}
              onChange={(value) => void toggleReminders(value)}
              label="Telegram hatırlatmaları"
              hint="Ekstre kesimi, yaklaşan son ödeme ve dönem özetleri bottan gönderilir."
            />
            {me.auth_source === "session" && (
              <>
                <div className="divider" />
                <div className="row between wrap">
                  <button type="button" className="btn secondary sm" onClick={() => setChangingPassword(true)}>
                    <Icon name="lock" size={16} />
                    Şifre değiştir
                  </button>
                  <button type="button" className="btn secondary sm" onClick={() => void logout()}>
                    <Icon name="logout" size={16} />
                    Çıkış yap
                  </button>
                </div>
              </>
            )}
          </Card>

          <Card
            title="Ödeme yöntemleri"
            flush
            action={
              <button type="button" className="btn secondary sm" onClick={() => setMethodEditing("new")}>
                <Icon name="plus" size={16} />
                Ekle
              </button>
            }
          >
            {state.error && (
              <div className="card-pad">
                <ErrorNote message={state.error} onRetry={state.reload} />
              </div>
            )}
            {!state.data && !state.error && <Loading />}
            {state.data && state.data.methods.length === 0 && <Empty icon="card" title="Ödeme yöntemi yok" />}
            {state.data && state.data.methods.length > 0 && (
              <div className="list">
                {state.data.methods.map((method) => {
                  const limit = limits.get(method.id);
                  const owner = ownerName(method.owner_user_id);
                  const details =
                    method.type === "credit_card"
                      ? [
                          method.statement_day ? `Kesim ayın ${method.statement_day}. günü` : "Kesim günü girilmemiş",
                          `son ödeme ${method.due_offset_days} gün sonra`,
                          limit ? `limit ${formatMinor(limit)}` : null,
                          owner,
                        ]
                      : ["Nakit", owner];
                  return (
                    <button
                      key={method.id}
                      type="button"
                      className={method.is_active ? "list-item" : "list-item inactive"}
                      onClick={() => setMethodEditing(method)}
                    >
                      <span className="list-icon">
                        <Icon name={method.type === "credit_card" ? "card" : "wallet"} size={18} />
                      </span>
                      <span className="list-main">
                        <span className="list-title">{method.name}</span>
                        <span className="list-sub">{details.filter(Boolean).join(" · ")}</span>
                      </span>
                      {!method.is_active && <span className="badge">Pasif</span>}
                      <Icon name="chevronRight" size={18} />
                    </button>
                  );
                })}
              </div>
            )}
          </Card>
        </div>

        <Card
          title="Kategoriler"
          flush
          action={
            <button type="button" className="btn secondary sm" onClick={() => setCategoryEditing("new")}>
              <Icon name="plus" size={16} />
              Ekle
            </button>
          }
        >
          {!state.data && !state.error && <Loading />}
          {state.data && (
            <div className="list">
              {state.data.categories.map((category) => (
                <button
                  key={category.id}
                  type="button"
                  className={category.is_active ? "list-item" : "list-item inactive"}
                  onClick={() => setCategoryEditing(category)}
                >
                  <span className="list-icon">{category.emoji || "🏷️"}</span>
                  <span className="list-main">
                    <span className="list-title">{category.name}</span>
                    <span className="list-sub">
                      {category.monthly_budget_minor
                        ? `Aylık hedef ${formatMinor(category.monthly_budget_minor)}`
                        : "Bütçe hedefi yok"}
                    </span>
                  </span>
                  {!category.is_active && <span className="badge">Pasif</span>}
                  <Icon name="chevronRight" size={18} />
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>

      {methodEditing && (
        <PaymentMethodForm
          method={methodEditing === "new" ? null : methodEditing}
          limitMinor={methodEditing === "new" ? null : limits.get(methodEditing.id) ?? null}
          onClose={() => setMethodEditing(null)}
          onSaved={(message) => {
            setMethodEditing(null);
            afterChange(message);
          }}
        />
      )}

      {categoryEditing && (
        <CategoryForm
          category={categoryEditing === "new" ? null : categoryEditing}
          onClose={() => setCategoryEditing(null)}
          onSaved={(message) => {
            setCategoryEditing(null);
            afterChange(message);
          }}
        />
      )}
    </>
  );
}

function PasswordForm({ onClose, onSaved }: { onClose: () => void; onSaved: (me: Me) => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (next.length < 8) return setError("Yeni şifre en az 8 karakter olmalıdır.");
    if (next !== repeat) return setError("Yeni şifreler aynı değil.");
    setBusy(true);
    setError(null);
    try {
      onSaved(await api.changePassword(current, next));
    } catch (cause: unknown) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Şifre değiştir"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Vazgeç
          </button>
          <button type="submit" form="password-form" className="btn primary" disabled={busy}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </>
      }
    >
      <form id="password-form" className="stack" onSubmit={submit} noValidate>
        <Field label="Mevcut şifre">
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
          />
        </Field>
        <Field label="Yeni şifre" hint="En az 8 karakter.">
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(event) => setNext(event.target.value)}
          />
        </Field>
        <Field label="Yeni şifre (tekrar)">
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            value={repeat}
            onChange={(event) => setRepeat(event.target.value)}
          />
        </Field>
        {error && (
          <div className="alert danger" role="alert">
            {error}
          </div>
        )}
      </form>
    </Modal>
  );
}

function intInRange(raw: string, min: number, max: number): number | null {
  const value = Number(raw);
  return Number.isInteger(value) && value >= min && value <= max ? value : null;
}

function PaymentMethodForm({
  method,
  limitMinor,
  onClose,
  onSaved,
}: {
  method: PaymentMethod | null;
  limitMinor: number | null;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const { users } = useSession();
  const toast = useToast();
  const [name, setName] = useState(method?.name ?? "");
  const [type, setType] = useState<PaymentMethodType>(method?.type ?? "credit_card");
  const [statementDay, setStatementDay] = useState(method?.statement_day ? String(method.statement_day) : "");
  const [dueOffset, setDueOffset] = useState(String(method?.due_offset_days ?? 10));
  const [cutoffInclusive, setCutoffInclusive] = useState(method?.cutoff_inclusive ?? true);
  const [ownerId, setOwnerId] = useState(method?.owner_user_id ? String(method.owner_user_id) : "");
  const [limit, setLimit] = useState(limitMinor ? minorToInput(limitMinor) : "");
  const [isActive, setIsActive] = useState(method?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isCard = type === "credit_card";

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!name.trim()) return setError("Bir ad yazın.");

    let statement: number | null = null;
    let offset = Number(dueOffset) || 10;
    if (isCard) {
      statement = intInRange(statementDay, 1, 31);
      if (statement === null) return setError("Hesap kesim günü 1 ile 31 arasında olmalıdır.");
      const parsedOffset = intInRange(dueOffset, 1, 60);
      if (parsedOffset === null) return setError("Son ödeme, kesimden 1 ile 60 gün sonra olmalıdır.");
      offset = parsedOffset;
    }
    const limitValue = limit.trim() ? parseAmountToMinor(limit) : null;
    if (limit.trim() && limitValue === null) return setError("Geçerli bir limit tutarı girin.");

    setBusy(true);
    setError(null);
    try {
      if (method) {
        const changes: Partial<PaymentMethodInput> = { name: name.trim(), is_active: isActive };
        if (isCard) {
          changes.statement_day = statement;
          changes.due_offset_days = offset;
          changes.cutoff_inclusive = cutoffInclusive;
          // Sunucuda sifir limit "limit yok" demektir.
          changes.credit_limit_minor = limitValue ?? 0;
        }
        if (ownerId) changes.owner_user_id = Number(ownerId);
        await api.updatePaymentMethod(method.id, changes);
        onSaved("Ödeme yöntemi güncellendi.");
      } else {
        await api.addPaymentMethod({
          name: name.trim(),
          type,
          statement_day: isCard ? statement : null,
          due_offset_days: offset,
          cutoff_inclusive: cutoffInclusive,
          owner_user_id: ownerId ? Number(ownerId) : null,
          credit_limit_minor: isCard ? limitValue : null,
        });
        onSaved("Ödeme yöntemi eklendi.");
      }
    } catch (cause: unknown) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={method ? "Ödeme yöntemini düzenle" : "Ödeme yöntemi ekle"}
      onClose={onClose}
      footer={
        <>
          {method && (
            <ConfirmButton
              label="Sil"
              icon="trash"
              onConfirm={async () => {
                try {
                  await api.deletePaymentMethod(method.id);
                  onSaved("Ödeme yöntemi silindi.");
                } catch (cause: unknown) {
                  toast(errorMessage(cause), "danger");
                }
              }}
            />
          )}
          <span className="spacer" />
          <button type="button" className="btn ghost" onClick={onClose}>
            Vazgeç
          </button>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void submit()}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </>
      }
    >
      <form className="form-grid two" onSubmit={submit} noValidate>
        {!method && (
          <Field label="Tür" className="full" group>
            <Segmented options={TYPE_OPTIONS} value={type} onChange={setType} />
          </Field>
        )}
        <Field label="Ad" className="full">
          <input
            className="input"
            maxLength={64}
            placeholder={isCard ? "Örn. Aykut Bonus Kart" : "Örn. Nakit"}
            autoFocus={!method}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>

        {isCard && (
          <>
            <Field label="Hesap kesim günü" hint="Ayın kaçıncı günü">
              <input
                className="input"
                type="number"
                inputMode="numeric"
                min={1}
                max={31}
                value={statementDay}
                onChange={(event) => setStatementDay(event.target.value)}
              />
            </Field>
            <Field label="Son ödeme" hint="Kesimden kaç gün sonra">
              <input
                className="input"
                type="number"
                inputMode="numeric"
                min={1}
                max={60}
                value={dueOffset}
                onChange={(event) => setDueOffset(event.target.value)}
              />
            </Field>
            <Field label="Kredi limiti" hint="Boş bırakılırsa limit takibi yapılmaz">
              <div className="input-wrap">
                <input
                  className="input"
                  inputMode="decimal"
                  placeholder="0,00"
                  value={limit}
                  onChange={(event) => setLimit(sanitiseAmount(event.target.value))}
                />
                <span className="suffix">TL</span>
              </div>
            </Field>
          </>
        )}

        <Field label="Sahibi" className={isCard ? undefined : "full"}>
          <select className="select" value={ownerId} onChange={(event) => setOwnerId(event.target.value)}>
            <option value="">Belirtilmemiş</option>
            {users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.display_name}
              </option>
            ))}
          </select>
        </Field>

        {isCard && (
          <div className="full">
            <Toggle
              checked={cutoffInclusive}
              onChange={setCutoffInclusive}
              label="Kesim günündeki harcamalar o ekstreye dahil"
              hint="Kapalıysa kesim günü yapılan harcama bir sonraki ekstreye düşer."
            />
          </div>
        )}
        {method && (
          <div className="full">
            <Toggle
              checked={isActive}
              onChange={setIsActive}
              label="Aktif"
              hint="Pasif yöntem yeni harcamalarda görünmez; geçmiş kayıtlar korunur."
            />
          </div>
        )}
        {method && isCard && (
          <p className="muted small full">
            Kart günlerindeki değişiklik yalnızca yeni harcamalara uygulanır; mevcut taksit planları
            değişmez.
          </p>
        )}
        {error && (
          <div className="alert danger full" role="alert">
            {error}
          </div>
        )}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}

function CategoryForm({
  category,
  onClose,
  onSaved,
}: {
  category: Category | null;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const toast = useToast();
  const [name, setName] = useState(category?.name ?? "");
  const [emoji, setEmoji] = useState(category?.emoji ?? "");
  const [budget, setBudget] = useState(
    category?.monthly_budget_minor ? minorToInput(category.monthly_budget_minor) : "",
  );
  const [isActive, setIsActive] = useState(category?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!name.trim()) return setError("Bir ad yazın.");
    const budgetValue = budget.trim() ? parseAmountToMinor(budget) : null;
    if (budget.trim() && budgetValue === null) return setError("Geçerli bir hedef tutarı girin.");

    setBusy(true);
    setError(null);
    try {
      if (category) {
        await api.updateCategory(category.id, {
          name: name.trim(),
          emoji: emoji.trim(),
          is_active: isActive,
          // Sunucuda sifir "hedefi kaldir" demektir.
          monthly_budget_minor: budgetValue ?? 0,
        });
        onSaved("Kategori güncellendi.");
      } else {
        await api.addCategory({
          name: name.trim(),
          emoji: emoji.trim(),
          monthly_budget_minor: budgetValue,
        });
        onSaved("Kategori eklendi.");
      }
    } catch (cause: unknown) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={category ? "Kategoriyi düzenle" : "Kategori ekle"}
      onClose={onClose}
      footer={
        <>
          {category && (
            <ConfirmButton
              label="Sil"
              icon="trash"
              onConfirm={async () => {
                try {
                  await api.deleteCategory(category.id);
                  onSaved("Kategori silindi.");
                } catch (cause: unknown) {
                  toast(errorMessage(cause), "danger");
                }
              }}
            />
          )}
          <span className="spacer" />
          <button type="button" className="btn ghost" onClick={onClose}>
            Vazgeç
          </button>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void submit()}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </>
      }
    >
      <form className="form-grid" onSubmit={submit} noValidate>
        <div className="form-grid emoji-name">
          <Field label="Simge">
            <input
              className="input center-text"
              maxLength={8}
              value={emoji}
              onChange={(event) => setEmoji(event.target.value)}
            />
          </Field>
          <Field label="Ad">
            <input
              className="input"
              maxLength={64}
              autoFocus={!category}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
        </div>
        <div className="chips">
          {EMOJI_SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              className={suggestion === emoji ? "chip active" : "chip"}
              onClick={() => setEmoji(suggestion)}
              aria-label={`Simge ${suggestion}`}
            >
              {suggestion}
            </button>
          ))}
        </div>
        <Field label="Aylık bütçe hedefi" hint="Boş bırakılırsa hedef takibi yapılmaz.">
          <div className="input-wrap">
            <input
              className="input"
              inputMode="decimal"
              placeholder="0,00"
              value={budget}
              onChange={(event) => setBudget(sanitiseAmount(event.target.value))}
            />
            <span className="suffix">TL</span>
          </div>
        </Field>
        {category && (
          <Toggle
            checked={isActive}
            onChange={setIsActive}
            label="Aktif"
            hint="Pasif kategori yeni harcamalarda görünmez; geçmiş kayıtlar korunur."
          />
        )}
        {error && (
          <div className="alert danger" role="alert">
            {error}
          </div>
        )}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}
