/**
 * Kurallar ve açıklama birleştirme.
 *
 * Kural "açıklamada X geçiyorsa kategoriyi, ödeme yöntemini veya açıklamayı
 * şuna çevir" der. Formda öneri olarak, içe aktarmada önizlemede kullanılır;
 * kişi isterse geçmiş harcamalara da uygulanır ve geri alınabilir.
 *
 * Birleştirme, "MIGROS 1234", "Migros" ve "migros kadıköy" gibi farklı
 * yazımları tek ada çevirir ve aynı yazım tekrar gelirse diye kural öğrenir.
 */

import { useState, type FormEvent } from "react";

import { api, type BulkResult, type MatchType, type Rule } from "../api";
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
import { useSession } from "../context";
import { errorMessage, useAsync } from "../hooks";

const MATCH_OPTIONS: readonly { value: MatchType; label: string }[] = [
  { value: "contains", label: "İçeriyorsa" },
  { value: "starts_with", label: "İle başlıyorsa" },
  { value: "equals", label: "Tam olarak buysa" },
];

const matchLabel = (type: MatchType) =>
  MATCH_OPTIONS.find((option) => option.value === type)?.label.toLowerCase() ?? type;

export function Rules() {
  const { bootstrap } = useSession();
  const toast = useToast();
  const state = useAsync(() => api.rules(), [], "rules");
  const [editing, setEditing] = useState<Rule | "new" | null>(null);
  const [confirmingRule, setConfirmingRule] = useState<{ rule: Rule; count: number } | null>(null);
  const [applyingRule, setApplyingRule] = useState(false);

  const categoryName = (id: number | null) => {
    const category = bootstrap.categories.find((item) => item.id === id);
    return category ? `${category.emoji} ${category.name}` : null;
  };
  const methodName = (id: number | null) =>
    bootstrap.payment_methods.find((item) => item.id === id)?.name ?? null;

  const undoToast = (result: BulkResult, message: string, after: () => void) => {
    if (result.previous.length === 0) {
      toast("Değişecek harcama bulunamadı.");
      return;
    }
    toast(message, "success", {
      label: "Geri al",
      run: async () => {
        await api.bulkRevert(result.previous);
        after();
      },
    });
  };

  const applyToPast = async (rule: Rule) => {
    try {
      const ids = await api.previewRule(rule.id);
      if (ids.length === 0) {
        toast("Bu kurala uyan ve değişecek geçmiş harcama yok.");
        return;
      }
      setConfirmingRule({ rule, count: ids.length });
    } catch (cause: unknown) {
      toast(errorMessage(cause), "danger");
    }
  };

  const confirmApplyRule = async () => {
    if (!confirmingRule) return;
    setApplyingRule(true);
    try {
      const result = await api.applyRule(confirmingRule.rule.id);
      setConfirmingRule(null);
      undoToast(result, `${result.changed.length} harcama güncellendi.`, () => undefined);
    } catch (cause: unknown) {
      toast(errorMessage(cause), "danger");
    } finally {
      setApplyingRule(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Kurallar"
        subtitle="Açıklamaya göre kategori önerisi ve açıklama düzeltme"
        actions={
          <button type="button" className="btn primary" onClick={() => setEditing("new")}>
            <Icon name="plus" size={18} />
            Kural ekle
          </button>
        }
      />

      <div className="grid two">
        <div className="stack">
          <Card title="Kurallar" flush>
            {state.error && (
              <div className="card-pad">
                <ErrorNote message={state.error} onRetry={state.reload} />
              </div>
            )}
            {!state.data && !state.error && <Loading />}
            {state.data && state.data.length === 0 && (
              <Empty
                icon="wand"
                title="Henüz kural yok"
                text="Örneğin “açıklamada shell geçiyorsa kategori Yakıt olsun”. Kurallar sırayla denenir; bir alanı ilk dolduran kazanır."
              />
            )}
            {state.data && state.data.length > 0 && (
              <div className="list">
                {state.data.map((rule) => (
                  <div className={rule.is_active ? "list-item rule-item" : "list-item rule-item inactive"} key={rule.id}>
                    <span className="list-icon">
                      <Icon name="wand" size={18} />
                    </span>
                    <span className="list-main">
                      <span className="list-title">
                        “{rule.pattern}” {matchLabel(rule.match_type)}
                      </span>
                      <span className="list-sub">
                        {[
                          categoryName(rule.set_category_id) && `→ ${categoryName(rule.set_category_id)}`,
                          methodName(rule.set_payment_method_id) && `→ ${methodName(rule.set_payment_method_id)}`,
                          rule.set_description && `→ “${rule.set_description}” olarak yaz`,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </span>
                    <span className="rule-actions">
                      <button
                        type="button"
                        className="btn ghost sm"
                        title="Geçmiş harcamalara uygula"
                        onClick={() => void applyToPast(rule)}
                      >
                        Geçmişe uygula
                      </button>
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label="Kuralı düzenle"
                        onClick={() => setEditing(rule)}
                      >
                        <Icon name="edit" size={16} />
                      </button>
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <RuleTester />
        </div>

        <MergeCard onMerged={undoToast} onRulesChanged={state.reload} />
      </div>

      {editing && (
        <RuleForm
          rule={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(message) => {
            setEditing(null);
            toast(message);
            state.reload();
          }}
        />
      )}

      {confirmingRule && (
        <Modal
          title="Kuralı geçmişe uygula"
          onClose={() => setConfirmingRule(null)}
          footer={
            <>
              <span className="spacer" />
              <button type="button" className="btn ghost" onClick={() => setConfirmingRule(null)}>
                Vazgeç
              </button>
              <button
                type="button"
                className="btn primary"
                disabled={applyingRule}
                onClick={() => void confirmApplyRule()}
              >
                {applyingRule ? "Uygulanıyor…" : `${confirmingRule.count} harcamayı güncelle`}
              </button>
            </>
          }
        >
          <p>
            <strong>“{confirmingRule.rule.pattern}”</strong> kuralına uyan{" "}
            <strong>{confirmingRule.count}</strong> geçmiş harcama güncellenecek. İşlem sonrasında
            tek tıkla geri alabilirsiniz.
          </p>
        </Modal>
      )}
    </>
  );
}

function RuleTester() {
  const { bootstrap } = useSession();
  const [text, setText] = useState("");
  const [result, setResult] = useState<string | null>(null);

  const test = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    try {
      const outcome = await api.testRules(text);
      if (outcome.rule_ids.length === 0) {
        setResult("Hiçbir kural uymadı.");
        return;
      }
      const category = bootstrap.categories.find((item) => item.id === outcome.category_id);
      const method = bootstrap.payment_methods.find((item) => item.id === outcome.payment_method_id);
      setResult(
        [
          category && `Kategori: ${category.emoji} ${category.name}`,
          method && `Ödeme: ${method.name}`,
          outcome.description && `Açıklama: “${outcome.description}”`,
        ]
          .filter(Boolean)
          .join(" · "),
      );
    } catch (cause: unknown) {
      setResult(errorMessage(cause));
    }
  };

  return (
    <Card title="Dene">
      <form className="row" onSubmit={test}>
        <input
          className="input"
          placeholder="Örn. MIGROS SANAL MARKET"
          aria-label="Denenecek açıklama"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setResult(null);
          }}
        />
        <button type="submit" className="btn secondary">
          Dene
        </button>
      </form>
      {result && <p className="mt-sm">{result}</p>}
    </Card>
  );
}

function RuleForm({
  rule,
  onClose,
  onSaved,
}: {
  rule: Rule | null;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const { bootstrap } = useSession();
  const toast = useToast();
  const [pattern, setPattern] = useState(rule?.pattern ?? "");
  const [matchType, setMatchType] = useState<MatchType>(rule?.match_type ?? "contains");
  const [categoryId, setCategoryId] = useState(rule?.set_category_id ? String(rule.set_category_id) : "");
  const [methodId, setMethodId] = useState(
    rule?.set_payment_method_id ? String(rule.set_payment_method_id) : "",
  );
  const [description, setDescription] = useState(rule?.set_description ?? "");
  const [active, setActive] = useState(rule?.is_active ?? true);
  const [order, setOrder] = useState(String(rule?.sort_order ?? 0));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!pattern.trim()) return setError("Aranacak metni yazın.");
    if (!categoryId && !methodId && !description.trim()) {
      return setError("Kural en az bir şeyi değiştirmeli.");
    }
    setBusy(true);
    setError(null);
    try {
      const payload = {
        pattern: pattern.trim(),
        match_type: matchType,
        set_category_id: categoryId ? Number(categoryId) : null,
        set_payment_method_id: methodId ? Number(methodId) : null,
        set_description: description.trim() || null,
        sort_order: Number(order) || 0,
        is_active: active,
      };
      if (rule) {
        const clear = [
          !categoryId && "set_category_id",
          !methodId && "set_payment_method_id",
          !description.trim() && "set_description",
        ].filter((item): item is string => Boolean(item));
        await api.updateRule(rule.id, { ...payload, clear });
        onSaved("Kural güncellendi.");
      } else {
        await api.addRule(payload);
        onSaved("Kural eklendi.");
      }
    } catch (cause: unknown) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={rule ? "Kuralı düzenle" : "Kural ekle"}
      onClose={onClose}
      footer={
        <>
          {rule && (
            <ConfirmButton
              label="Sil"
              icon="trash"
              onConfirm={async () => {
                try {
                  await api.deleteRule(rule.id);
                  onSaved("Kural silindi.");
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
      <form className="stack" onSubmit={submit} noValidate>
        <Field
          label="Açıklama"
          hint="Büyük/küçük harf, Türkçe karakter ve #etiketler fark etmez."
        >
          <input
            className="input"
            maxLength={120}
            autoFocus={!rule}
            placeholder="Örn. shell"
            value={pattern}
            onChange={(event) => setPattern(event.target.value)}
          />
        </Field>
        <Field label="Eşleşme" group>
          <Segmented options={MATCH_OPTIONS} value={matchType} onChange={setMatchType} />
        </Field>
        <Field label="Kategoriyi şu yap">
          <select className="select" value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
            <option value="">Değiştirme</option>
            {bootstrap.categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.emoji} {category.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Ödeme yöntemini şu yap" hint="Yalnızca formda ve içe aktarmada önerilir; geçmişe uygulanmaz.">
          <select className="select" value={methodId} onChange={(event) => setMethodId(event.target.value)}>
            <option value="">Değiştirme</option>
            {bootstrap.payment_methods.map((method) => (
              <option key={method.id} value={method.id}>
                {method.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Açıklamayı şuna çevir" hint="Örn. “MIGROS 1234 İSTANBUL” → “Migros”. Etiketler korunur.">
          <input
            className="input"
            maxLength={120}
            placeholder="Değiştirme"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <Field label="Sıra" hint="Küçük sayı önce denenir. Özel kuralı genelden önce koyun.">
          <input
            className="input"
            type="number"
            value={order}
            onChange={(event) => setOrder(event.target.value)}
          />
        </Field>
        <Toggle checked={active} onChange={setActive} label="Etkin" />
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

function MergeCard({
  onMerged,
  onRulesChanged,
}: {
  onMerged: (result: BulkResult, message: string, after: () => void) => void;
  onRulesChanged: () => void;
}) {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const state = useAsync(() => api.descriptions(submitted), [submitted]);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [target, setTarget] = useState("");
  const [learn, setLearn] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const merge = async () => {
    if (chosen.size === 0) return setError("Birleştirilecek açıklamaları seçin.");
    if (!target.trim()) return setError("Yeni açıklamayı yazın.");
    setBusy(true);
    setError(null);
    try {
      const result = await api.mergeDescriptions([...chosen], target.trim(), learn);
      onMerged(result, `${result.changed.length} harcamanın açıklaması “${target.trim()}” yapıldı.`, state.reload);
      setChosen(new Set());
      state.reload();
      if (learn) onRulesChanged();
    } catch (cause: unknown) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Açıklamaları birleştir">
      <div className="stack">
        <p className="muted small">
          Aynı yerin farklı yazımlarını seçip tek bir ada çevirin. Etiketler korunur.
        </p>
        <form
          className="row"
          onSubmit={(event) => {
            event.preventDefault();
            setSubmitted(query.trim());
          }}
        >
          <input
            className="input"
            placeholder="Ara, örn. migros"
            aria-label="Açıklama ara"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="submit" className="btn secondary">
            <Icon name="search" size={16} />
            Ara
          </button>
        </form>
        {state.error && <ErrorNote message={state.error} onRetry={state.reload} />}
        {!state.data && !state.error && <Loading />}
        {state.data && state.data.length === 0 && <p className="muted small">Eşleşen açıklama yok.</p>}
        {state.data && state.data.length > 0 && (
          <div className="list bordered">
            {state.data.map((group) => (
              <label className="list-item" key={group.key}>
                <input
                  type="checkbox"
                  className="list-check"
                  checked={chosen.has(group.key)}
                  onChange={() => {
                    setChosen((current) => {
                      const next = new Set(current);
                      if (next.has(group.key)) next.delete(group.key);
                      else next.add(group.key);
                      return next;
                    });
                    if (!target) setTarget(group.sample);
                  }}
                />
                <span className="list-main">
                  <span className="list-title">{group.sample}</span>
                  <span className="list-sub">{group.count} harcama</span>
                </span>
                <span className="list-end">
                  <span className="list-amount">{group.total.formatted}</span>
                </span>
              </label>
            ))}
          </div>
        )}
        <Field label="Yeni açıklama">
          <input
            className="input"
            maxLength={120}
            placeholder="Örn. Migros"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
          />
        </Field>
        <Toggle
          checked={learn}
          onChange={setLearn}
          label="Bu yazımlar tekrar gelirse de düzelt"
          hint="Her eski yazım için bir kural eklenir."
        />
        {error && (
          <div className="alert danger" role="alert">
            {error}
          </div>
        )}
        <div className="form-actions start">
          <button
            type="button"
            className="btn primary"
            disabled={busy || chosen.size === 0}
            onClick={() => void merge()}
          >
            {busy ? "Birleştiriliyor…" : `${chosen.size} yazımı birleştir`}
          </button>
        </div>
      </div>
    </Card>
  );
}
