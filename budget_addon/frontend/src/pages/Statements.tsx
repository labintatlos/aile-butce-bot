/**
 * Ekstre: bankanın CSV dökümünü içe aktarma ve kart ekstresi mutabakatı.
 *
 * İçe aktarmada dosya sunucuda okunur, sütunlar tahmin edilir ve bir önizleme
 * gelir. Kopya olduğu düşünülen ve önceki alışverişlerin taksiti olan satırlar
 * seçili gelmez. Hiçbir satır kişi "Aktar" demeden kaydedilmez.
 *
 * Mutabakatta bankanın ekstre tutarı yazılır ve sistemin hesabıyla
 * karşılaştırılır; satırlar bankada görüldükçe işaretlenir.
 */

import { useEffect, useMemo, useState } from "react";

import {
  api,
  type ColumnMapping,
  type ImportPreview,
  type ImportPreviewRow,
  type ImportSign,
  type ReconcileDetail,
} from "../api";
import { Icon } from "../components/icons";
import {
  Card,
  Empty,
  ErrorNote,
  Field,
  Loading,
  Modal,
  PageHeader,
  Segmented,
  useToast,
} from "../components/ui";
import { useSession } from "../context";
import {
  formatMinor,
  installmentLabel,
  longDate,
  minorToInput,
  parseAmountToMinor,
  sanitiseAmount,
  shortDate,
} from "../format";
import { errorMessage, useAsync } from "../hooks";

type Tab = "import" | "reconcile";

const TABS: readonly { value: Tab; label: string }[] = [
  { value: "import", label: "CSV içe aktar" },
  { value: "reconcile", label: "Ekstre mutabakatı" },
];

export function Statements() {
  const [tab, setTab] = useState<Tab>("import");
  return (
    <>
      <PageHeader title="Ekstre" subtitle="Bankanın dökümünü aktarın, ekstreyle karşılaştırın" />
      <div className="tabs-row">
        <Segmented options={TABS} value={tab} onChange={setTab} mode="tablist" />
      </div>
      {tab === "import" ? <ImportPanel /> : <ReconcilePanel />}
    </>
  );
}

// ---------------------------------------------------------------------------
// Ice aktarma
// ---------------------------------------------------------------------------

const SIGNS: readonly { value: ImportSign; label: string }[] = [
  { value: "auto", label: "Kendisi bulsun" },
  { value: "positive", label: "Harcamalar artı (kart ekstresi)" },
  { value: "negative", label: "Harcamalar eksi (hesap dökümü)" },
];

type Encoding = "auto" | "utf-8" | "windows-1254";

const ENCODINGS: readonly { value: Encoding; label: string }[] = [
  { value: "auto", label: "Otomatik" },
  { value: "utf-8", label: "UTF-8" },
  { value: "windows-1254", label: "Türkçe Windows" },
];

const SKIP_LABELS: Record<string, string> = {
  opposite_sign: "Ödeme veya gelir",
  zero: "Tutar sıfır",
  unreadable: "Okunamadı",
};

const SOURCE_LABELS: Record<string, string> = {
  rule: "kural",
  history: "geçmiş",
  default: "varsayılan",
};

function decode(buffer: ArrayBuffer, encoding: Encoding): string {
  if (encoding !== "auto") return new TextDecoder(encoding).decode(buffer);
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(buffer);
  } catch {
    // Turk bankalarinin cogu Excel'den Windows-1254 ile kaydeder.
    return new TextDecoder("windows-1254").decode(buffer);
  }
}

interface RowEdit {
  selected: boolean;
  category_id: number | null;
  description: string;
  amount: string;
  installment_count: number;
}

function ImportPanel() {
  const { bootstrap } = useSession();
  const toast = useToast();
  const methods = bootstrap.payment_methods;
  const [methodId, setMethodId] = useState<number | null>(
    () => (methods.find((method) => method.type === "credit_card") ?? methods[0])?.id ?? null,
  );
  const [defaultCategory, setDefaultCategory] = useState<number | null>(null);
  const [sign, setSign] = useState<ImportSign>("auto");
  const [encoding, setEncoding] = useState<Encoding>("auto");
  const [buffer, setBuffer] = useState<ArrayBuffer | null>(null);
  const [fileName, setFileName] = useState("");
  const [mapping, setMapping] = useState<ColumnMapping | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [edits, setEdits] = useState<Record<number, RowEdit>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const method = methods.find((item) => item.id === methodId);
  const isCard = method?.type === "credit_card";

  const runPreview = async (nextMapping: ColumnMapping | null = mapping) => {
    if (!buffer || methodId === null) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.importPreview({
        text: decode(buffer, encoding),
        payment_method_id: methodId,
        default_category_id: defaultCategory,
        sign,
        mapping: nextMapping,
      });
      setPreview(result);
      setMapping(result.mapping);
      setEdits(
        Object.fromEntries(
          result.rows.map((row) => [
            row.index,
            {
              selected: row.selected,
              category_id: row.category_id,
              description: row.description,
              amount: minorToInput(row.amount.minor),
              installment_count: row.installment_count,
            },
          ]),
        ),
      );
    } catch (cause: unknown) {
      setPreview(null);
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  // Dosya, kart, isaret veya kodlama degisince onizleme yeniden alinir;
  // elle yapilan sutun secimi yeni dosyada gecerli olmayabilir, sifirlanir.
  useEffect(() => {
    setMapping(null);
    void runPreview(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buffer, methodId, sign, encoding, defaultCategory]);

  const rows = preview?.rows ?? [];
  const chosen = rows.filter((row) => edits[row.index]?.selected && !row.skip_reason);
  const chosenTotal = chosen.reduce(
    (sum, row) => sum + (parseAmountToMinor(edits[row.index].amount) ?? 0),
    0,
  );
  const missingCategory = chosen.some((row) => edits[row.index].category_id === null);

  const edit = (index: number, change: Partial<RowEdit>) =>
    setEdits((current) => ({ ...current, [index]: { ...current[index], ...change } }));

  const commit = async () => {
    if (methodId === null || chosen.length === 0) return;
    if (missingCategory) return setError("Seçili her satırın kategorisini seçin.");
    setBusy(true);
    setError(null);
    try {
      const result = await api.importCommit(
        chosen.map((row) => {
          const value = edits[row.index];
          return {
            transaction_date: row.transaction_date as string,
            description: value.description.trim() || null,
            amount_minor: parseAmountToMinor(value.amount) ?? row.amount.minor,
            category_id: value.category_id as number,
            payment_method_id: row.payment_method_id ?? methodId,
            installment_count: isCard ? value.installment_count : 1,
            is_shared: true,
          };
        }),
      );
      toast(`${result.created} harcama aktarıldı (${result.total.formatted}).`, "success", {
        label: "Geri al",
        run: async () => {
          await api.bulkDelete(result.expense_ids);
        },
      });
      setBuffer(null);
      setFileName("");
      setPreview(null);
    } catch (cause: unknown) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <Card title="1. Dosya ve kart">
        <div className="form-grid two">
          <Field label="Hangi kart veya hesap?">
            <select
              className="select"
              value={methodId ?? ""}
              onChange={(event) => setMethodId(Number(event.target.value))}
            >
              {methods.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Kategori bulunamazsa" hint="Kural ve geçmiş kayıtlar önce denenir.">
            <select
              className="select"
              value={defaultCategory ?? ""}
              onChange={(event) =>
                setDefaultCategory(event.target.value ? Number(event.target.value) : null)
              }
            >
              <option value="">Boş bırak, ben seçeyim</option>
              {bootstrap.categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.emoji} {category.name}
                </option>
              ))}
            </select>
          </Field>
          <label className="file-drop full">
            <Icon name="upload" size={24} />
            <strong>{fileName || "CSV dosyası seçin"}</strong>
            <span className="small">
              Bankanızın internet şubesinden ekstreyi veya hesap hareketlerini CSV olarak indirin.
              Excel dosyasını önce "CSV (noktalı virgülle ayrılmış)" olarak kaydedin.
            </span>
            <input
              type="file"
              accept=".csv,.txt,text/csv,text/plain"
              onChange={async (event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (!file) return;
                if (file.size > 2_000_000) {
                  setError("Dosya çok büyük. En fazla 2 MB'lık bir ekstre yükleyin.");
                  return;
                }
                setFileName(file.name);
                setBuffer(await file.arrayBuffer());
              }}
            />
          </label>
          <Field label="Tutarların işareti" group>
            <Segmented options={SIGNS} value={sign} onChange={setSign} />
          </Field>
          <Field label="Karakter kodlaması" group hint="Türkçe harfler bozuk görünürse değiştirin.">
            <Segmented options={ENCODINGS} value={encoding} onChange={setEncoding} />
          </Field>
        </div>
      </Card>

      {error && <ErrorNote message={error} />}
      {busy && !preview && <Loading label="Dosya okunuyor…" />}

      {preview && mapping && (
        <Card title="2. Sütunlar" action={busy ? <span className="spinner" /> : undefined}>
          <p className="muted small mb-sm">
            Sütunlar başlıktan tahmin edildi. Yanlışsa düzeltin; önizleme yenilenir.
          </p>
          <div className="mapping-grid">
            {(
              [
                ["date_column", "Tarih"],
                ["description_column", "Açıklama"],
                ["amount_column", "Tutar"],
              ] as const
            ).map(([key, label]) => (
              <Field key={key} label={label}>
                <select
                  className="select"
                  value={mapping[key]}
                  onChange={(event) => {
                    const next = { ...mapping, [key]: Number(event.target.value) };
                    setMapping(next);
                    void runPreview(next);
                  }}
                >
                  {preview.columns.map((column, index) => (
                    <option key={index} value={index}>
                      {column}
                    </option>
                  ))}
                </select>
              </Field>
            ))}
            <Field label="İlk veri satırı">
              <input
                className="input"
                type="number"
                min={1}
                value={mapping.first_row + 1}
                onChange={(event) => {
                  const value = Math.max(1, Number(event.target.value) || 1);
                  const next = { ...mapping, first_row: value - 1 };
                  setMapping(next);
                  void runPreview(next);
                }}
              />
            </Field>
          </div>
        </Card>
      )}

      {preview && (
        <Card title="3. Önizleme" flush>
          {rows.length === 0 ? (
            <Empty icon="list" title="Aktarılacak satır bulunamadı" />
          ) : (
            <div className="table-wrap">
              <table className="table compact import-table">
                <thead>
                  <tr>
                    <th className="select-col" />
                    <th>Tarih</th>
                    <th>Açıklama</th>
                    <th>Kategori</th>
                    {isCard && <th>Taksit</th>}
                    <th className="right">Tutar</th>
                    <th>Durum</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <PreviewLine
                      key={row.index}
                      row={row}
                      value={edits[row.index]}
                      isCard={isCard}
                      onChange={(change) => edit(row.index, change)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="card-pad row between wrap">
            <span>
              <strong>{chosen.length}</strong> satır seçili · {formatMinor(chosenTotal)}
            </span>
            <button
              type="button"
              className="btn primary"
              disabled={busy || chosen.length === 0}
              onClick={() => void commit()}
            >
              <Icon name="check" size={16} />
              {busy ? "Aktarılıyor…" : `${chosen.length} harcamayı aktar`}
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}

function PreviewLine({
  row,
  value,
  isCard,
  onChange,
}: {
  row: ImportPreviewRow;
  value: RowEdit | undefined;
  isCard: boolean;
  onChange: (change: Partial<RowEdit>) => void;
}) {
  const { bootstrap } = useSession();
  if (!value) return null;
  const skipped = Boolean(row.skip_reason);
  return (
    <tr className={value.selected && !skipped ? undefined : "is-off"}>
      <td className="select-col">
        <input
          type="checkbox"
          aria-label="Aktar"
          disabled={skipped}
          checked={value.selected && !skipped}
          onChange={(event) => onChange({ selected: event.target.checked })}
        />
      </td>
      <td>{row.transaction_date ? shortDate(row.transaction_date) : "—"}</td>
      <td style={{ minWidth: 180 }}>
        <input
          className="input"
          aria-label="Açıklama"
          disabled={skipped}
          value={value.description}
          onChange={(event) => onChange({ description: event.target.value })}
        />
      </td>
      <td style={{ minWidth: 160 }}>
        <select
          className="select"
          aria-label="Kategori"
          disabled={skipped}
          value={value.category_id ?? ""}
          onChange={(event) =>
            onChange({ category_id: event.target.value ? Number(event.target.value) : null })
          }
        >
          <option value="">Seçin</option>
          {bootstrap.categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.emoji} {category.name}
            </option>
          ))}
        </select>
        {row.category_source && value.category_id === row.category_id && (
          <span className="muted small">{SOURCE_LABELS[row.category_source]}</span>
        )}
      </td>
      {isCard && (
        <td>
          <select
            className="select"
            aria-label="Taksit"
            disabled={skipped}
            value={value.installment_count}
            onChange={(event) => onChange({ installment_count: Number(event.target.value) })}
          >
            {Array.from({ length: bootstrap.max_installments }, (_, index) => index + 1).map((count) => (
              <option key={count} value={count}>
                {installmentLabel(count)}
              </option>
            ))}
          </select>
        </td>
      )}
      <td className="right" style={{ minWidth: 110 }}>
        <input
          className="input"
          style={{ textAlign: "right" }}
          inputMode="decimal"
          aria-label="Tutar"
          disabled={skipped}
          value={value.amount}
          onChange={(event) => onChange({ amount: sanitiseAmount(event.target.value) })}
        />
      </td>
      <td className="wrap" style={{ minWidth: 140 }}>
        {row.skip_reason && <span className="badge">{SKIP_LABELS[row.skip_reason]}</span>}
        {row.duplicate_of && <span className="badge danger">Kayıtlı: {row.duplicate_of}</span>}
        {row.installment_current && (
          <span className="badge accent">
            {row.installment_current}. taksit
          </span>
        )}
        {row.note && <div className="muted small">{row.note}</div>}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Mutabakat
// ---------------------------------------------------------------------------

function ReconcilePanel() {
  const { bootstrap } = useSession();
  const cards = bootstrap.payment_methods.filter((method) => method.type === "credit_card");
  const [cardId, setCardId] = useState<number | null>(cards[0]?.id ?? null);
  const [open, setOpen] = useState<string | null>(null);
  const state = useAsync(
    () => (cardId === null ? Promise.resolve([]) : api.reconcileStatements(cardId)),
    [cardId],
  );

  if (cards.length === 0) {
    return (
      <Card>
        <Empty icon="card" title="Kredi kartı tanımlı değil" text="Mutabakat yalnızca kredi kartlarında yapılır." />
      </Card>
    );
  }

  return (
    <div className="stack">
      <Field label="Kart">
        <select
          className="select"
          value={cardId ?? ""}
          onChange={(event) => setCardId(Number(event.target.value))}
        >
          {cards.map((card) => (
            <option key={card.id} value={card.id}>
              {card.name}
            </option>
          ))}
        </select>
      </Field>
      {state.error && <ErrorNote message={state.error} onRetry={state.reload} />}
      {!state.data && !state.error && <Loading />}
      {state.data && (
        <Card title="Ekstreler" flush>
          {state.data.length === 0 ? (
            <Empty icon="card" title="Bu karta düşmüş ekstre yok" />
          ) : (
            <div className="list">
              {state.data.map((item) => (
                <button
                  key={item.statement_date}
                  type="button"
                  className="list-item"
                  onClick={() => setOpen(item.statement_date)}
                >
                  <span className="list-icon">
                    <Icon name={item.is_reconciled ? "check" : "card"} size={18} />
                  </span>
                  <span className="list-main">
                    <span className="list-title">{longDate(item.statement_date)} ekstresi</span>
                    <span className="list-sub">
                      Son ödeme {shortDate(item.due_date)} · {item.cleared_count}/{item.line_count} satır
                      işaretli
                    </span>
                  </span>
                  <span className="list-end">
                    <span className="list-amount">{item.ours_total.formatted}</span>
                    <span className="list-sub">
                      {item.bank_total === null ? (
                        "Karşılaştırılmadı"
                      ) : item.is_reconciled ? (
                        <span className="success-text">
                          <Icon name="check" size={12} /> Mutabık{item.changed_since ? " (sonra değişti)" : ""}
                        </span>
                      ) : (
                        <span className="danger-text">
                          <Icon name="alert" size={12} /> Fark {item.difference?.formatted}
                        </span>
                      )}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </Card>
      )}
      {open && cardId !== null && (
        <ReconcileModal
          cardId={cardId}
          statementDate={open}
          onClose={() => setOpen(null)}
          onChanged={state.reload}
        />
      )}
    </div>
  );
}

function ReconcileModal({
  cardId,
  statementDate,
  onClose,
  onChanged,
}: {
  cardId: number;
  statementDate: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const toast = useToast();
  const state = useAsync(() => api.reconcileDetail(cardId, statementDate), [cardId, statementDate]);
  const [detail, setDetail] = useState<ReconcileDetail | null>(null);
  const [bank, setBank] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const current = detail ?? state.data;

  useEffect(() => {
    if (state.data) {
      setBank(state.data.summary.bank_total ? minorToInput(state.data.summary.bank_total.minor) : "");
      setNote(state.data.note ?? "");
    }
  }, [state.data]);

  const installmentIds = useMemo(
    () => (current?.lines ?? []).filter((line) => line.kind === "installment").map((line) => line.id),
    [current],
  );

  const mark = async (ids: number[], cleared: boolean) => {
    try {
      setDetail(await api.reconcileMark(cardId, statementDate, ids, cleared));
      onChanged();
    } catch (cause: unknown) {
      toast(errorMessage(cause), "danger");
    }
  };

  const save = async () => {
    const minor = parseAmountToMinor(bank);
    if (minor === null) {
      toast("Bankanın ekstre tutarını girin.", "danger");
      return;
    }
    setBusy(true);
    try {
      const next = await api.reconcileSave(cardId, statementDate, minor, note.trim() || null);
      setDetail(next);
      onChanged();
      toast(next.summary.is_reconciled ? "Ekstre mutabık." : `Fark var: ${next.summary.difference?.formatted}`,
        next.summary.is_reconciled ? "success" : "danger");
    } catch (cause: unknown) {
      toast(errorMessage(cause), "danger");
    } finally {
      setBusy(false);
    }
  };

  const bankMinor = parseAmountToMinor(bank);
  const liveDifference = current && bankMinor !== null ? bankMinor - current.summary.ours_total.minor : null;

  return (
    <Modal
      title={`${longDate(statementDate)} ekstresi`}
      onClose={onClose}
      wide
      footer={
        <>
          <span className="spacer" />
          <button type="button" className="btn ghost" onClick={onClose}>
            Kapat
          </button>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void save()}>
            {busy ? "Kaydediliyor…" : "Karşılaştırmayı kaydet"}
          </button>
        </>
      }
    >
      {!current ? (
        state.error ? <ErrorNote message={state.error} onRetry={state.reload} /> : <Loading />
      ) : (
        <div className="stack">
          <div className="diff-box">
            <div>
              <span>Sistemin hesabı</span>
              <strong>{current.summary.ours_total.formatted}</strong>
            </div>
            <div>
              <span>Bankanın ekstresi</span>
              <div className="input-wrap">
                <input
                  className="input"
                  inputMode="decimal"
                  placeholder="0,00"
                  aria-label="Bankanın ekstre tutarı"
                  value={bank}
                  onChange={(event) => setBank(sanitiseAmount(event.target.value))}
                />
                <span className="suffix">TL</span>
              </div>
            </div>
            <div>
              <span>Fark</span>
              <strong
                className={
                  liveDifference === null ? "muted" : liveDifference === 0 ? "success-text" : "danger-text"
                }
              >
                {liveDifference === null
                  ? "—"
                  : liveDifference === 0
                    ? "Yok, mutabık"
                    : formatMinor(liveDifference)}
              </strong>
            </div>
          </div>
          {liveDifference !== null && liveDifference > 0 && (
            <p className="muted small">
              Banka daha fazla diyor: sistemde girilmemiş bir harcama olabilir. İşaretlenmemiş satırları
              ve bankadaki satırları karşılaştırın.
            </p>
          )}
          {liveDifference !== null && liveDifference < 0 && (
            <p className="muted small">
              Sistem daha fazla diyor: bir harcama yanlış karta, yanlış tutarla girilmiş ya da iadesi
              kaydedilmemiş olabilir.
            </p>
          )}
          <Field label="Not">
            <input
              className="input"
              maxLength={200}
              placeholder="İsteğe bağlı"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </Field>

          <div className="row between wrap">
            <h3 className="section-title">Satırlar</h3>
            <span className="row">
              <button type="button" className="btn ghost sm" onClick={() => void mark(installmentIds, true)}>
                Tümünü işaretle
              </button>
              <button type="button" className="btn ghost sm" onClick={() => void mark(installmentIds, false)}>
                İşaretleri kaldır
              </button>
            </span>
          </div>
          <p className="muted small">
            Bankanın ekstresinde gördüğünüz satırları işaretleyin. İşaretli toplam:{" "}
            <strong>{current.cleared_total.formatted}</strong>
          </p>
          <div className="list bordered">
            {current.lines.map((line) => (
              <label className="list-item" key={`${line.kind}-${line.id}`}>
                <input
                  type="checkbox"
                  className="list-check"
                  disabled={line.kind === "refund"}
                  checked={line.cleared}
                  onChange={(event) => void mark([line.id], event.target.checked)}
                />
                <span className="list-main">
                  <span className="list-title">{line.description || line.public_id}</span>
                  <span className="list-sub">
                    {shortDate(line.transaction_date)} · {line.public_id}
                    {line.installment_count && line.installment_count > 1
                      ? ` · ${line.installment_number}/${line.installment_count} taksit`
                      : ""}
                  </span>
                </span>
                <span className="list-end">
                  <span className={line.amount.minor < 0 ? "list-amount success-text" : "list-amount"}>
                    {line.amount.formatted}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </div>
      )}
    </Modal>
  );
}
