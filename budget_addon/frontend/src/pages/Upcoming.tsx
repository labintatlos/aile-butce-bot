/**
 * Yaklaşanlar: önümüzdeki günlerin sabit giderleri, ekstre kesimleri, son
 * ödemeleri ve birikim hedefi tarihleri tek listede.
 *
 * Tutarlar ya sabit gider şablonundan ya da kayıtlı taksitlerden gelir;
 * tahmin yürütülmez.
 */

import { useMemo, useState } from "react";

import { api, type EventKind, type UpcomingEvent } from "../api";
import { Icon, type IconName } from "../components/icons";
import { Card, Empty, ErrorNote, Loading, PageHeader, Segmented, Stat } from "../components/ui";
import { useSession } from "../context";
import { formatMinor, longDate } from "../format";
import { useAsync } from "../hooks";

const SPANS = [
  { value: "14", label: "2 hafta" },
  { value: "30", label: "30 gün" },
  { value: "60", label: "60 gün" },
  { value: "90", label: "90 gün" },
] as const;

const KIND_INFO: Record<EventKind, { label: string; icon: IconName }> = {
  card_due: { label: "Son ödeme", icon: "alert" },
  recurring: { label: "Sabit gider", icon: "repeat" },
  statement: { label: "Ekstre kesimi", icon: "card" },
  savings_goal: { label: "Birikim hedefi", icon: "wallet" },
};

const WEEKDAYS = ["Pazar", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"];

function dayLabel(iso: string, today: string): string {
  if (iso === today) return "Bugün";
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  const [ty, tm, td] = today.split("-").map(Number);
  const diff = Math.round((date.getTime() - new Date(ty, tm - 1, td).getTime()) / 86_400_000);
  if (diff === 1) return "Yarın";
  return `${WEEKDAYS[date.getDay()]} · ${diff} gün sonra`;
}

export function UpcomingList({ events, today }: { events: UpcomingEvent[]; today: string }) {
  const days = useMemo(() => {
    const map = new Map<string, UpcomingEvent[]>();
    for (const event of events) map.set(event.when, [...(map.get(event.when) ?? []), event]);
    return [...map.entries()];
  }, [events]);

  if (days.length === 0) {
    return <Empty icon="calendar" title="Bu aralıkta yaklaşan ödeme yok" />;
  }
  return (
    <>
      {days.map(([when, items]) => (
        <div className="day-group" key={when}>
          <div className="day-head">
            <span>{longDate(when)}</span>
            <span>{dayLabel(when, today)}</span>
          </div>
          <div className="list bordered">
            {items.map((event, index) => (
              <div className="list-item" key={`${event.kind}-${event.title}-${index}`}>
                <span className={`list-icon event-icon ${event.kind}`}>
                  <Icon name={KIND_INFO[event.kind].icon} size={18} />
                </span>
                <span className="list-main">
                  <span className="list-title">{event.title}</span>
                  <span className="list-sub">
                    {KIND_INFO[event.kind].label}
                    {event.detail ? ` · ${event.detail}` : ""}
                  </span>
                </span>
                {event.amount && (
                  <span className="list-end">
                    <span className="list-amount">{event.amount.formatted}</span>
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </>
  );
}

export function Upcoming() {
  const { bootstrap } = useSession();
  const [span, setSpan] = useState<"14" | "30" | "60" | "90">("30");
  const state = useAsync(() => api.upcomingEvents(Number(span)), [span]);

  const totals = useMemo(() => {
    const events = state.data ?? [];
    const sum = (kind: EventKind) =>
      events.filter((event) => event.kind === kind).reduce((total, event) => total + (event.amount?.minor ?? 0), 0);
    return { due: sum("card_due"), recurring: sum("recurring") };
  }, [state.data]);

  return (
    <>
      <PageHeader
        title="Yaklaşanlar"
        subtitle="Sabit giderler, ekstre kesimleri ve son ödemeler"
        actions={<Segmented options={SPANS} value={span} onChange={setSpan} />}
      />
      {state.error && <ErrorNote message={state.error} onRetry={state.reload} />}
      {!state.data && !state.error && <Loading />}
      {state.data && (
        <div className="stack">
          <div className="grid stats pair">
            <Stat label="Kart son ödemeleri" value={formatMinor(totals.due)} icon="card" />
            <Stat label="Sabit giderler" value={formatMinor(totals.recurring)} icon="repeat" />
          </div>
          <Card>
            <UpcomingList events={state.data} today={bootstrap.today} />
          </Card>
          <p className="muted small">
            Ekstre tutarı, o ekstreye bugüne kadar düşen taksitlerin toplamıdır; kesim gününe kadar
            yapılacak harcamalarla artabilir.
          </p>
        </div>
      )}
    </>
  );
}
