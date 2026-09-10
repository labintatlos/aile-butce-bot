/**
 * Fiş fotoğrafı: ekleme, görüntüleme, değiştirme ve kaldırma.
 *
 * Fotoğraf yüklenmeden önce tarayıcıda küçültülür: telefon kameralarının
 * birkaç megabaytlık görüntüleri fişi okumak için gereksizdir ve mobil veride
 * yavaş yüklenir. Küçültme başarısız olursa özgün dosya gönderilir.
 */

import { useRef, useState } from "react";

import { api } from "../api";
import { errorMessage } from "../hooks";
import { Icon } from "./icons";
import { ConfirmButton, useToast } from "./ui";

const MAX_EDGE = 1600;
const JPEG_QUALITY = 0.82;

async function shrink(file: File): Promise<Blob> {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY),
    );
    return blob ?? file;
  } catch {
    return file;
  }
}

export function ReceiptPanel({
  expenseId,
  hasReceipt,
  onChange,
}: {
  expenseId: number;
  hasReceipt: boolean;
  onChange: (hasReceipt: boolean) => void;
}) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(() => Date.now());

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    try {
      await api.uploadReceipt(expenseId, await shrink(file));
      setVersion(Date.now());
      onChange(true);
      toast("Fiş fotoğrafı eklendi.");
    } catch (cause: unknown) {
      toast(errorMessage(cause), "danger");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  const url = api.receiptUrl(expenseId, version);

  return (
    <div>
      <input
        ref={input}
        type="file"
        accept="image/*"
        hidden
        onChange={(event) => void upload(event.target.files?.[0])}
      />
      {hasReceipt ? (
        <>
          <a href={url} target="_blank" rel="noreferrer">
            <img
              src={url}
              alt="Fiş fotoğrafı"
              style={{ display: "block", maxWidth: "100%", maxHeight: 320, borderRadius: 12 }}
            />
          </a>
          <div className="row wrap mt">
            <button
              type="button"
              className="btn secondary sm"
              disabled={busy}
              onClick={() => input.current?.click()}
            >
              <Icon name="edit" size={16} />
              {busy ? "Yükleniyor…" : "Değiştir"}
            </button>
            <ConfirmButton
              label="Kaldır"
              confirmLabel="Evet, kaldır"
              icon="trash"
              className="btn danger-ghost sm"
              onConfirm={async () => {
                try {
                  await api.deleteReceipt(expenseId);
                  onChange(false);
                  toast("Fiş fotoğrafı kaldırıldı.");
                } catch (cause: unknown) {
                  toast(errorMessage(cause), "danger");
                }
              }}
            />
          </div>
        </>
      ) : (
        <button
          type="button"
          className="btn secondary"
          disabled={busy}
          onClick={() => input.current?.click()}
        >
          <Icon name="plus" size={18} />
          {busy ? "Yükleniyor…" : "Fiş fotoğrafı ekle"}
        </button>
      )}
    </div>
  );
}
