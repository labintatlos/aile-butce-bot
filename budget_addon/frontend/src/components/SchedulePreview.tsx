import type { SchedulePreview } from "../api";
import { longDate } from "../format";

interface Props {
  preview: SchedulePreview;
}

/**
 * Kaydetmeden önce gösterilen finansal özet (§17).
 *
 * Buradaki tüm sayılar sunucudan gelir; istemci hesaplama yapmaz. Böylece
 * önizlemede görülen tutar ile kaydedilen tutar arasında fark oluşamaz.
 */
export function SchedulePreviewCard({ preview }: Props) {
  return (
    <section className="preview" aria-label="Kayıt önizlemesi">
      <div className="preview-row">
        <span>Toplam</span>
        <strong>{preview.total.formatted}</strong>
      </div>
      <div className="preview-row">
        <span>Taksit</span>
        <strong>
          {preview.installment_count} x {preview.installment_amount.formatted}
        </strong>
      </div>
      {preview.first_statement_date && (
        <div className="preview-row">
          <span>İlk ekstre</span>
          <strong>{longDate(preview.first_statement_date)}</strong>
        </div>
      )}
      {preview.first_due_date && (
        <div className="preview-row">
          <span>İlk son ödeme</span>
          <strong>{longDate(preview.first_due_date)}</strong>
        </div>
      )}
      {preview.last_due_date && preview.installment_count > 1 && (
        <div className="preview-row">
          <span>Son taksit</span>
          <strong>{longDate(preview.last_due_date)}</strong>
        </div>
      )}
    </section>
  );
}
