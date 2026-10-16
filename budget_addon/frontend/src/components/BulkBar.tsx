/**
 * Seçilen harcamalara toplu işlem: kategori, ortak/kişisel, etiket ve silme.
 *
 * Her işlem sunucuda tek seferde yapılır ve önceki değerleri döndürür; bildirim
 * üzerindeki "Geri al" o değerleri aynen geri yazar.
 */

import { useState } from "react";

import { api, type BulkChanges, type BulkResult } from "../api";
import { useSession } from "../context";
import { errorMessage } from "../hooks";
import { Icon } from "./icons";
import { useToast } from "./ui";

const SHARED = "shared";

export function BulkBar({
  ids,
  onClear,
  onSelectAll,
  onDone,
}: {
  ids: number[];
  onClear: () => void;
  onSelectAll: () => void;
  onDone: () => void;
}) {
  const { bootstrap } = useSession();
  const toast = useToast();
  const [tag, setTag] = useState("");
  const [busy, setBusy] = useState(false);

  const undoable = (result: BulkResult, message: string) => {
    const skipped = Object.keys(result.skipped).length;
    const text = skipped
      ? `${message} ${skipped} bölünmüş harcamanın kategorisi değişmedi.`
      : message;
    if (result.previous.length === 0) {
      toast(skipped ? text : "Değişecek bir şey yoktu.");
      return;
    }
    toast(text, "success", {
      label: "Geri al",
      run: async () => {
        await api.bulkRevert(result.previous);
        onDone();
      },
    });
  };

  const run = async (changes: BulkChanges, message: string) => {
    setBusy(true);
    try {
      const result = await api.bulkUpdate(ids, changes);
      undoable(result, message);
      onDone();
      onClear();
    } catch (cause: unknown) {
      toast(errorMessage(cause), "danger");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      const result = await api.bulkDelete(ids);
      toast(`${result.changed.length} harcama silindi.`, "success", {
        label: "Geri al",
        run: async () => {
          await api.bulkRestore(result.changed);
          onDone();
        },
      });
      onDone();
      onClear();
    } catch (cause: unknown) {
      toast(errorMessage(cause), "danger");
    } finally {
      setBusy(false);
    }
  };

  const cleanTag = tag.trim().replace(/^#/, "");

  return (
    <div className="bulk-bar" role="toolbar" aria-label="Seçilen harcamalar">
      <strong>{ids.length} seçili</strong>
      <button type="button" className="btn ghost sm" onClick={onSelectAll}>
        Sayfadakilerin tümü
      </button>
      <select
        className="select"
        aria-label="Kategoriyi değiştir"
        value=""
        disabled={busy || ids.length === 0}
        onChange={(event) => {
          const id = Number(event.target.value);
          const category = bootstrap.categories.find((item) => item.id === id);
          if (category) void run({ category_id: id }, `Kategori ${category.name} yapıldı.`);
        }}
      >
        <option value="">Kategori…</option>
        {bootstrap.categories.map((category) => (
          <option key={category.id} value={category.id}>
            {category.emoji} {category.name}
          </option>
        ))}
      </select>
      <select
        className="select"
        aria-label="Kimin harcaması"
        value=""
        disabled={busy || ids.length === 0}
        onChange={(event) => {
          const value = event.target.value;
          if (value === SHARED) void run({ is_shared: true }, "Ortak gider yapıldı.");
          else if (value) {
            const person = bootstrap.people.find((item) => String(item.id) === value);
            void run(
              { is_shared: false, owner_user_id: Number(value) },
              `${person?.display_name ?? ""} kişisel yapıldı.`.trim(),
            );
          }
        }}
      >
        <option value="">Kimin…</option>
        <option value={SHARED}>Ortak</option>
        {bootstrap.people.map((person) => (
          <option key={person.id} value={person.id}>
            {person.display_name} kişisel
          </option>
        ))}
      </select>
      <input
        className="input"
        placeholder="#etiket"
        aria-label="Etiket"
        maxLength={40}
        value={tag}
        onChange={(event) => setTag(event.target.value)}
      />
      <button
        type="button"
        className="btn secondary sm"
        disabled={busy || !cleanTag || ids.length === 0}
        onClick={() => void run({ add_tag: cleanTag }, `#${cleanTag} eklendi.`)}
      >
        <Icon name="tag" size={16} />
        Ekle
      </button>
      <button
        type="button"
        className="btn ghost sm"
        disabled={busy || !cleanTag || ids.length === 0}
        onClick={() => void run({ remove_tag: cleanTag }, `#${cleanTag} kaldırıldı.`)}
      >
        Kaldır
      </button>
      <span className="spacer" />
      <button
        type="button"
        className="btn danger-ghost sm"
        disabled={busy || ids.length === 0}
        onClick={() => void remove()}
      >
        <Icon name="trash" size={16} />
        Sil
      </button>
      <button type="button" className="btn ghost sm" onClick={onClear}>
        Vazgeç
      </button>
    </div>
  );
}
