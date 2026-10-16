/**
 * Hesaplar: bakiyeler, hesaplar arası transfer, kart ödemesi ve net varlık.
 *
 * Bakiye bankadan okunmaz; kişi zaman zaman günceller. Transfer harcama ya da
 * gelir değildir, yalnızca iki hesabın bakiyesini değiştirir. Net varlık,
 * hesapların toplamından ödenmemiş kart taksitlerinin düşülmesidir.
 */

import { useState, type FormEvent } from "react";

import { api, type Account, type AccountKind, type AccountsOverview } from "../api";
import { NetWorthLine } from "../components/charts";
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
  Stat,
  Toggle,
  useToast,
} from "../components/ui";
import { useSession } from "../context";
import { longDate, parseAmountToMinor, sanitiseAmount, shortDate } from "../format";
import { errorMessage, useAsync } from "../hooks";

const KINDS: readonly { value: AccountKind; label: string }[] = [
  { value: "bank", label: "Vadesiz" },
  { value: "cash", label: "Nakit" },
  { value: "savings", label: "Birikim" },
  { value: "investment", label: "Yatırım" },
  { value: "other", label: "Diğer" },
];

const kindLabel = (kind: AccountKind) => KINDS.find((item) => item.value === kind)?.label ?? kind;

export function Accounts() {
  const state = useAsync(() => api.accounts(), []);
  const [overview, setOverview] = useState<AccountsOverview | null>(null);
  const [adding, setAdding] = useState(false);
  const [transferring, setTransferring] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const data = overview ?? state.data;
  const open = data?.accounts.find((account) => account.id === openId) ?? null;

  const reload = () => {
    setOverview(null);
    state.reload();
  };

  return (
    <>
      <PageHeader
        title="Hesaplar"
        subtitle="Bakiyeler, transferler ve net varlık"
        actions={
          <>
            <button
              type="button"
              className="btn secondary"
              disabled={!data || data.accounts.length === 0}
              onClick={() => setTransferring(true)}
            >
              <Icon name="transfer" size={18} />
              Transfer
            </button>
            <button type="button" className="btn primary" onClick={() => setAdding(true)}>
              <Icon name="plus" size={18} />
              Hesap ekle
            </button>
          </>
        }
      />

      {state.error && <ErrorNote message={state.error} onRetry={state.reload} />}
      {!data && !state.error && <Loading />}

      {data && (
        <div className="stack">
          <div className="grid stats">
            <Stat
              label="Net varlık"
              value={data.today.net.formatted}
              tone={data.today.net.minor < 0 ? "danger" : undefined}
              icon="trend"
            />
            <Stat label="Hesapların toplamı" value={data.today.assets.formatted} icon="bank" />
            <Stat label="Ödenmemiş kart borcu" value={data.today.card_debt.formatted} icon="card" />
          </div>

          <Card title="Net varlık" action={<span className="muted small">Ay sonları ve bugün</span>}>
            <NetWorthLine points={[...data.history, data.today]} />
          </Card>

          <Card title="Hesaplar" flush>
            {data.accounts.length === 0 ? (
              <Empty
                icon="bank"
                title="Henüz hesap yok"
                text="Vadesiz hesabınızı, birikim hesabınızı veya cebinizdeki nakdi ekleyin; bakiyesini zaman zaman güncelleyin."
                action={
                  <button type="button" className="btn primary" onClick={() => setAdding(true)}>
                    Hesap ekle
                  </button>
                }
              />
            ) : (
              <div className="list">
                {data.accounts.map((account) => (
                  <button
                    key={account.id}
                    type="button"
                    className={account.is_active ? "list-item" : "list-item inactive"}
                    onClick={() => setOpenId(account.id)}
                  >
                    <span className="list-icon">
                      <Icon name={account.kind === "cash" ? "wallet" : "bank"} size={18} />
                    </span>
                    <span className="list-main">
                      <span className="list-title">{account.name}</span>
                      <span className="list-sub">
                        {kindLabel(account.kind)}
                        {account.last_balance_date
                          ? ` · bakiye ${shortDate(account.last_balance_date)} tarihinde girildi`
                          : " · bakiye girilmedi"}
                      </span>
                    </span>
                    <span className="list-end">
                      <span className={account.balance.minor < 0 ? "list-amount danger-text" : "list-amount"}>
                        {account.balance.formatted}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </Card>
          <p className="muted small">
            Kart borcu, son ödeme tarihi gelmemiş taksitlerden hesaplanır. Birikim hedeflerine ayrılan
            para zaten bir hesapta durduğu için ayrıca eklenmez.
          </p>
        </div>
      )}

      {adding && (
        <AccountForm
          onClose={() => setAdding(false)}
          onSaved={(next) => {
            setAdding(false);
            setOverview(next);
          }}
        />
      )}
      {transferring && data && (
        <TransferForm
          accounts={data.accounts.filter((account) => account.is_active)}
          onClose={() => setTransferring(false)}
          onSaved={() => {
            setTransferring(false);
            reload();
          }}
        />
      )}
      {open && (
        <AccountDetail
          account={open}
          onClose={() => setOpenId(null)}
          onChanged={reload}
        />
      )}
    </>
  );
}

function SignedAmount({
  label,
  value,
  negative,
  onValue,
  onNegative,
  negativeLabel,
  hint,
}: {
  label: string;
  value: string;
  negative: boolean;
  onValue: (value: string) => void;
  onNegative: (value: boolean) => void;
  negativeLabel: string;
  hint?: string;
}) {
  return (
    <>
      <Field label={label} hint={hint}>
        <div className="input-wrap">
          <input
            className="input"
            inputMode="decimal"
            placeholder="0,00"
            value={value}
            onChange={(event) => onValue(sanitiseAmount(event.target.value))}
          />
          <span className="suffix">TL</span>
        </div>
      </Field>
      <Toggle checked={negative} onChange={onNegative} label={negativeLabel} />
    </>
  );
}

function AccountForm({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: (next: AccountsOverview) => void;
}) {
  const { bootstrap } = useSession();
  const toast = useToast();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<AccountKind>("bank");
  const [balance, setBalance] = useState("");
  const [negative, setNegative] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!name.trim()) return setError("Hesaba bir ad verin.");
    let opening: number | null = null;
    if (balance.trim()) {
      const minor = parseAmountToMinor(balance);
      if (minor === null && balance.replace(/[0,.]/g, "") !== "") return setError("Bakiye geçerli değil.");
      opening = (minor ?? 0) * (negative ? -1 : 1);
    }
    setBusy(true);
    setError(null);
    try {
      const next = await api.addAccount({
        name: name.trim(),
        kind,
        opening_balance_minor: opening,
        opening_date: bootstrap.today,
        notes: null,
      });
      toast("Hesap eklendi.");
      onSaved(next);
    } catch (cause: unknown) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Hesap ekle"
      onClose={onClose}
      footer={
        <>
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
      <form className="stack" onSubmit={submit} noValidate>
        <Field label="Ad">
          <input
            className="input"
            maxLength={64}
            autoFocus
            placeholder="Örn. Ziraat vadesiz"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field label="Tür" group>
          <Segmented options={KINDS} value={kind} onChange={setKind} />
        </Field>
        <SignedAmount
          label="Bugünkü bakiye"
          hint="İsteğe bağlı; sonra da girebilirsiniz."
          value={balance}
          negative={negative}
          onValue={setBalance}
          onNegative={setNegative}
          negativeLabel="Eksi bakiye (ek hesap borcu)"
        />
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

function TransferForm({
  accounts,
  onClose,
  onSaved,
}: {
  accounts: Account[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { bootstrap } = useSession();
  const toast = useToast();
  const cards = bootstrap.payment_methods.filter((method) => method.type === "credit_card");
  const [from, setFrom] = useState(String(accounts[0]?.id ?? ""));
  const [to, setTo] = useState("");
  const [amount, setAmount] = useState("");
  const [when, setWhen] = useState(bootstrap.today);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const minor = parseAmountToMinor(amount);
    if (!from) return setError("Paranın çıktığı hesabı seçin.");
    if (!to) return setError("Paranın gittiği yeri seçin.");
    if (minor === null) return setError("Geçerli bir tutar girin.");
    setBusy(true);
    setError(null);
    try {
      await api.transfer({
        from_account_id: Number(from),
        to_account_id: to.startsWith("a") ? Number(to.slice(1)) : null,
        payment_method_id: to.startsWith("c") ? Number(to.slice(1)) : null,
        amount_minor: minor,
        entry_date: when,
        note: note.trim() || null,
      });
      toast(to.startsWith("c") ? "Kart ödemesi kaydedildi." : "Transfer kaydedildi.");
      onSaved();
    } catch (cause: unknown) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Transfer veya kart ödemesi"
      onClose={onClose}
      footer={
        <>
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
        <Field label="Nereden">
          <select className="select" value={from} onChange={(event) => setFrom(event.target.value)}>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Nereye">
          <select className="select" value={to} onChange={(event) => setTo(event.target.value)}>
            <option value="">Seçin</option>
            <optgroup label="Hesaplar">
              {accounts
                .filter((account) => String(account.id) !== from)
                .map((account) => (
                  <option key={account.id} value={`a${account.id}`}>
                    {account.name}
                  </option>
                ))}
            </optgroup>
            {cards.length > 0 && (
              <optgroup label="Kart ödemesi">
                {cards.map((card) => (
                  <option key={card.id} value={`c${card.id}`}>
                    {card.name}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </Field>
        <Field label="Tutar">
          <div className="input-wrap">
            <input
              className="input"
              inputMode="decimal"
              placeholder="0,00"
              value={amount}
              onChange={(event) => setAmount(sanitiseAmount(event.target.value))}
            />
            <span className="suffix">TL</span>
          </div>
        </Field>
        <Field label="Tarih">
          <input className="input" type="date" value={when} onChange={(event) => setWhen(event.target.value)} />
        </Field>
        <Field label="Not" className="full">
          <input
            className="input"
            maxLength={200}
            placeholder="İsteğe bağlı"
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </Field>
        <p className="muted small full">
          Transfer harcama ya da gelir sayılmaz. Kart ödemesi yalnızca hesabın bakiyesini düşürür; kart
          borcu zaten taksitlerden hesaplanır.
        </p>
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

const ENTRY_LABELS = { balance: "Bakiye", transfer: "Transfer", adjustment: "Düzeltme" } as const;

const ACTIONS = [
  { value: "balance", label: "Bakiye güncelle" },
  { value: "adjustment", label: "Faiz / masraf" },
  { value: "edit", label: "Düzenle" },
] as const;

function AccountDetail({
  account,
  onClose,
  onChanged,
}: {
  account: Account;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { bootstrap } = useSession();
  const toast = useToast();
  const entries = useAsync(() => api.accountEntries(account.id), [account.id]);
  const [action, setAction] = useState<(typeof ACTIONS)[number]["value"]>("balance");
  const [amount, setAmount] = useState("");
  const [negative, setNegative] = useState(false);
  const [when, setWhen] = useState(bootstrap.today);
  const [note, setNote] = useState("");
  const [name, setName] = useState(account.name);
  const [kind, setKind] = useState<AccountKind>(account.kind);
  const [active, setActive] = useState(account.is_active);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const after = (message: string) => {
    toast(message);
    setAmount("");
    setNote("");
    setNegative(false);
    entries.reload();
    onChanged();
  };

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    setError(null);
    try {
      setBusy(true);
      if (action === "edit") {
        if (!name.trim()) return setError("Hesaba bir ad verin.");
        await api.updateAccount(account.id, { name: name.trim(), kind, is_active: active });
        after("Hesap güncellendi.");
        return;
      }
      const minor = parseAmountToMinor(amount);
      if (minor === null && !(action === "balance" && /^0*[,.]?0*$/.test(amount) && amount)) {
        return setError("Geçerli bir tutar girin.");
      }
      const signed = (minor ?? 0) * (negative ? -1 : 1);
      if (action === "balance") {
        await api.setBalance(account.id, signed, when, note.trim() || null);
        after("Bakiye kaydedildi.");
      } else {
        await api.addAdjustment(account.id, signed, when, note.trim() || null);
        after("Düzeltme kaydedildi.");
      }
    } catch (cause: unknown) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={account.name}
      onClose={onClose}
      wide
      footer={
        <>
          <ConfirmButton
            label="Hesabı sil"
            icon="trash"
            onConfirm={async () => {
              try {
                await api.deleteAccount(account.id);
                toast("Hesap silindi.");
                onChanged();
                onClose();
              } catch (cause: unknown) {
                toast(errorMessage(cause), "danger");
              }
            }}
          />
          <span className="spacer" />
          <button type="button" className="btn primary" disabled={busy} onClick={() => void submit()}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </>
      }
    >
      <div className="stack">
        <div className="detail-head">
          <span className="list-icon large">
            <Icon name={account.kind === "cash" ? "wallet" : "bank"} size={24} />
          </span>
          <div className="list-main">
            <div className="detail-amount">{account.balance.formatted}</div>
            <div className="muted">{kindLabel(account.kind)}</div>
          </div>
        </div>

        <Segmented options={ACTIONS} value={action} onChange={setAction} />

        <form className="form-grid two" onSubmit={submit} noValidate>
          {action === "edit" ? (
            <>
              <Field label="Ad">
                <input className="input" maxLength={64} value={name} onChange={(event) => setName(event.target.value)} />
              </Field>
              <Field label="Tür">
                <select className="select" value={kind} onChange={(event) => setKind(event.target.value as AccountKind)}>
                  {KINDS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </Field>
              <div className="full">
                <Toggle
                  checked={active}
                  onChange={setActive}
                  label="Aktif"
                  hint="Pasif hesap net varlığa katılmaz; geçmişi korunur."
                />
              </div>
            </>
          ) : (
            <>
              <div className="full stack">
                <SignedAmount
                  label={action === "balance" ? "Hesaptaki bakiye" : "Tutar"}
                  hint={
                    action === "balance"
                      ? "Bankanın gösterdiği bakiye. Sonraki transferler bunun üzerine eklenir."
                      : "Faiz geliri artı, banka masrafı eksi girilir."
                  }
                  value={amount}
                  negative={negative}
                  onValue={setAmount}
                  onNegative={setNegative}
                  negativeLabel={action === "balance" ? "Eksi bakiye" : "Azalış (masraf, kesinti)"}
                />
              </div>
              <Field label="Tarih">
                <input className="input" type="date" value={when} onChange={(event) => setWhen(event.target.value)} />
              </Field>
              <Field label="Not">
                <input
                  className="input"
                  maxLength={200}
                  placeholder="İsteğe bağlı"
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                />
              </Field>
            </>
          )}
          {error && (
            <div className="alert danger full" role="alert">
              {error}
            </div>
          )}
          <button type="submit" hidden />
        </form>

        <h3 className="section-title">Hareketler</h3>
        {entries.error && <ErrorNote message={entries.error} onRetry={entries.reload} />}
        {entries.data && entries.data.length === 0 && <p className="muted small">Henüz hareket yok.</p>}
        {entries.data && entries.data.length > 0 && (
          <div className="list bordered">
            {entries.data.map((entry) => (
              <div className="list-item" key={entry.id}>
                <span className="list-main">
                  <span className="list-title">
                    {ENTRY_LABELS[entry.kind]}
                    {entry.kind === "balance" ? "" : entry.amount.minor > 0 ? " · giriş" : " · çıkış"}
                  </span>
                  <span className="list-sub">
                    {longDate(entry.entry_date)}
                    {entry.note ? ` · ${entry.note}` : ""}
                  </span>
                </span>
                <span className="list-end">
                  <span className="list-amount">{entry.amount.formatted}</span>
                </span>
                <ConfirmButton
                  label=""
                  icon="trash"
                  className="icon-btn"
                  confirmLabel="Sil"
                  onConfirm={async () => {
                    try {
                      await api.deleteAccountEntry(entry.id);
                      toast(entry.transfer_group ? "Transferin iki ayağı da silindi." : "Hareket silindi.");
                      entries.reload();
                      onChanged();
                    } catch (cause: unknown) {
                      toast(errorMessage(cause), "danger");
                    }
                  }}
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </Modal>
  );
}
