/**
 * Site içi bildirimler: hatırlatmalar, bütçe ve kart limiti uyarıları.
 *
 * Sayfa açılınca bildirimler okundu sayılır; yeni olanlar bu ziyarette yine
 * "Yeni" olarak işaretli görünür ki hangisinin yeni geldiği kaybolmasın.
 */

import { useEffect } from "react";

import { api, NOTIFICATIONS_CHANGED_EVENT } from "../api";
import { Icon } from "../components/icons";
import { Card, Empty, ErrorNote, Loading, PageHeader } from "../components/ui";
import { useSession } from "../context";
import { isRoute, useAsync } from "../hooks";

function when(value: string): string {
  return new Date(value).toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" });
}

export function Notifications() {
  const { navigate } = useSession();
  const state = useAsync(() => api.notifications(50), []);

  useEffect(() => {
    if (!state.data?.unread) return;
    api.markNotificationsRead().then(
      () => window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED_EVENT)),
      () => undefined,
    );
  }, [state.data]);

  return (
    <>
      <PageHeader
        title="Bildirimler"
        subtitle="Hatırlatmalar ve uyarılar"
        actions={
          <button type="button" className="btn secondary" onClick={() => navigate("ayarlar")}>
            <Icon name="settings" size={18} />
            Bildirim ayarları
          </button>
        }
      />

      {state.error && <ErrorNote message={state.error} onRetry={state.reload} />}
      {!state.data && state.loading && <Loading />}

      {state.data && state.data.items.length === 0 && (
        <Empty
          icon="bell"
          title="Henüz bildirim yok"
          text="Ekstre kesimi, son ödeme, bütçe ve kart limiti uyarıları burada görünür."
        />
      )}

      {state.data && state.data.items.length > 0 && (
        <Card flush>
          <div className="list">
            {state.data.items.map((item) => {
              const target = item.link && isRoute(item.link) ? item.link : null;
              return (
                <div key={item.id} className="list-item">
                  <span className="list-icon">
                    <Icon name="bell" size={18} />
                  </span>
                  <span className="list-main">
                    <span className="list-title">
                      {item.title} {!item.is_read && <span className="badge accent">Yeni</span>}
                    </span>
                    <span className="list-sub" style={{ whiteSpace: "pre-line" }}>
                      {item.body}
                    </span>
                    <span className="muted small">{when(item.created_at)}</span>
                  </span>
                  {target && (
                    <button type="button" className="btn ghost sm" onClick={() => navigate(target)}>
                      Aç
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </>
  );
}
