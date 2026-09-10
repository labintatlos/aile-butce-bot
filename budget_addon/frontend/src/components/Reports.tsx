/**
 * Rapor ekranı.
 *
 * Form vardı, rapor yoktu: sayıları görmek için Telegram'a dönmek gerekiyordu.
 * Bu ekran aynı verileri panelde de gösterir.
 *
 * Grafikler için kütüphane kullanılmaz. Buradaki her şey oran çubuğu ve
 * dikey sütundur; ikisi de birkaç satır CSS ile çizilir. Bir grafik paketi
 * eklemek, iki kişilik bir bütçe uygulamasının paket boyutunu birkaç kat
 * artırmaktan başka bir işe yaramazdı.
 *
 * Hiçbir tutar burada hesaplanmaz. Sunucu her sayıyı hem kuruş hem
 * biçimlenmiş metin olarak gönderir; istemci yalnızca yerleştirir.
 */

import { useEffect, useState } from "react";

import { ApiError, reports, type ReportBundle } from "../api";
import { barWidth, monthName, shortMonthName } from "../format";

export function Reports() {
  const [data, setData] = useState<ReportBundle | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    reports
      .load()
      .then(setData)
      .catch((cause: unknown) =>
        setError(cause instanceof ApiError ? cause.message : "Raporlar yüklenemedi."),
      );
  }, []);

  if (error) {
    return (
      <main className="screen">
        <p className="error" role="alert">
          {error}
        </p>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="screen">
        <p className="hint">Yükleniyor…</p>
      </main>
    );
  }

  const { spending, position, budgets, cards, forecast, settlement, year } = data;

  return (
    <main className="screen">
      <header className="header">
        <h1>{monthName(spending.year, spending.month)}</h1>
        <p className="hint">
          {spending.transaction_count} işlem · {spending.total.formatted}
        </p>
      </header>

      <PositionCard position={position} forecast={forecast} />
      <CategoryBreakdown items={spending.by_category} total={spending.total.minor} />
      {budgets.length > 0 && <BudgetList items={budgets} />}
      {cards.length > 0 && <CardList items={cards} />}
      {settlement.shared_total.minor > 0 && <SettlementCard settlement={settlement} />}
      <YearChart year={year} />
    </main>
  );
}

function PositionCard({
  position,
  forecast,
}: {
  position: ReportBundle["position"];
  forecast: ReportBundle["forecast"];
}) {
  const short = position.remaining.minor < 0;
  return (
    <section className="card">
      <h2 className="card-title">Bu ayın durumu</h2>
      <dl className="rows">
        <Row label="Gelir" value={position.income.formatted} />
        <Row label="Kart ödemeleri" value={position.card_due.formatted} />
        <Row label="Nakit harcama" value={position.cash_spent.formatted} />
        {position.expected_recurring.minor > 0 && (
          <Row
            label="Bekleyen sabit gider"
            value={position.expected_recurring.formatted}
          />
        )}
        <Row
          label={short ? "Açık" : "Kalan"}
          value={position.remaining.formatted}
          tone={short ? "danger" : "strong"}
        />
      </dl>
      <p className="hint">
        Bu gidişle ay sonu: <strong>{forecast.total.formatted}</strong> (
        {forecast.days_elapsed}/{forecast.days_in_month} gün)
      </p>
    </section>
  );
}

function CategoryBreakdown({
  items,
  total,
}: {
  items: ReportBundle["spending"]["by_category"];
  total: number;
}) {
  if (items.length === 0) {
    return (
      <section className="card">
        <h2 className="card-title">Kategoriler</h2>
        <p className="hint">Bu ay henüz harcama kaydı yok.</p>
      </section>
    );
  }

  return (
    <section className="card">
      <h2 className="card-title">Kategoriler</h2>
      {items.map((item) => {
        // Oran yalnizca cubugun genisligi icindir; gosterilen tutar
        // sunucudan geldigi gibi kalir.
        const ratio = total > 0 ? (item.total.minor * 100) / total : 0;
        return (
          <div className="bar-row" key={item.id}>
            <div className="bar-label">
              <span>
                {item.emoji} {item.name}
              </span>
              <span>{item.total.formatted}</span>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: barWidth(ratio) }} />
            </div>
          </div>
        );
      })}
    </section>
  );
}

function BudgetList({ items }: { items: ReportBundle["budgets"] }) {
  return (
    <section className="card">
      <h2 className="card-title">Bütçe hedefleri</h2>
      {items.map((item) => (
        <div className="bar-row" key={item.category_id}>
          <div className="bar-label">
            <span>
              {item.emoji} {item.name}
            </span>
            <span className={item.is_exceeded ? "danger" : undefined}>
              {item.spent.formatted} / {item.budget.formatted}
            </span>
          </div>
          <div className="bar-track">
            <div
              className={item.is_exceeded ? "bar-fill danger-fill" : "bar-fill"}
              style={{ width: barWidth(item.ratio) }}
            />
          </div>
          <p className="hint">
            %{item.ratio} ·{" "}
            {item.is_exceeded ? "hedef aşıldı" : `kalan ${item.remaining.formatted}`}
          </p>
        </div>
      ))}
    </section>
  );
}

function CardList({ items }: { items: ReportBundle["cards"] }) {
  return (
    <section className="card">
      <h2 className="card-title">Kartlar</h2>
      {items.map((item) => (
        <div className="bar-row" key={item.payment_method_id}>
          <div className="bar-label">
            <span>{item.name}</span>
            <span className={item.is_over_limit ? "danger" : undefined}>
              {item.outstanding.formatted}
            </span>
          </div>
          {item.credit_limit ? (
            <>
              <div className="bar-track">
                <div
                  className={item.is_over_limit ? "bar-fill danger-fill" : "bar-fill"}
                  style={{ width: barWidth(item.ratio) }}
                />
              </div>
              <p className="hint">
                %{item.ratio} ·{" "}
                {item.is_over_limit
                  ? "limit aşıldı"
                  : `kullanılabilir ${item.available.formatted}`}
              </p>
            </>
          ) : (
            <p className="hint">Limit girilmemiş</p>
          )}
        </div>
      ))}
    </section>
  );
}

function SettlementCard({ settlement }: { settlement: ReportBundle["settlement"] }) {
  return (
    <section className="card">
      <h2 className="card-title">Ortak gider denkleştirmesi</h2>
      <dl className="rows">
        <Row label="Ortak gider" value={settlement.shared_total.formatted} />
        {settlement.balances.map((person) => (
          <Row
            key={person.user_id}
            label={person.name}
            value={`${person.paid.formatted} / pay ${person.share.formatted}`}
          />
        ))}
      </dl>
      <p className={settlement.is_even ? "hint" : "hint strong"}>
        {settlement.is_even
          ? "Hesap denk."
          : `${settlement.debtor_name}, ${settlement.creditor_name} kişisine ${settlement.transfer.formatted} vermeli.`}
      </p>
    </section>
  );
}

function YearChart({ year }: { year: ReportBundle["year"] }) {
  const peak = Math.max(...year.months.map((item) => item.this_year.minor), 1);
  const recorded = year.months.some((item) => item.this_year.minor > 0);

  return (
    <section className="card">
      <h2 className="card-title">{year.year} ayları</h2>
      {recorded ? (
        <>
          <div className="columns">
            {year.months.map((item) => (
              <div className="column" key={item.month} title={item.this_year.formatted}>
                <div
                  className="column-fill"
                  style={{ height: barWidth((item.this_year.minor * 100) / peak) }}
                />
                <span className="column-label">{shortMonthName(item.month)}</span>
              </div>
            ))}
          </div>
          <dl className="rows">
            <Row label={String(year.year)} value={year.this_year_total.formatted} />
            <Row label={String(year.year - 1)} value={year.last_year_total.formatted} />
          </dl>
        </>
      ) : (
        <p className="hint">Bu yıl henüz kayıt yok.</p>
      )}
    </section>
  );
}

function Row({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "danger" | "strong";
}) {
  return (
    <div className="row">
      <dt>{label}</dt>
      <dd className={tone}>{value}</dd>
    </div>
  );
}
