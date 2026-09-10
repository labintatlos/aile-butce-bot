/**
 * Bildirim ayarları: hatırlatmalar, bu cihazdaki anlık bildirim ve e-posta.
 *
 * Anlık bildirim cihaza özgüdür: telefonda açmak bilgisayarda açmaz. E-posta
 * seçeneği yalnızca yönetici eklenti ayarlarında bir e-posta sunucusu
 * tanımladıysa gösterilir.
 */

import { useEffect, useState } from "react";

import { api, NOTIFICATIONS_CHANGED_EVENT } from "../api";
import { useSession } from "../context";
import { errorMessage, useAsync } from "../hooks";
import { disablePush, enablePush, readPushState, type PushState } from "../push";
import { Icon } from "./icons";
import { Card, ErrorNote, Field, Loading, Toggle, useToast } from "./ui";

const PUSH_HINTS: Record<PushState, string> = {
  unsupported:
    "Bu tarayıcı anlık bildirimi desteklemiyor ya da site HTTPS adresinden açılmadı.",
  "needs-install":
    "iPhone'da önce Safari'de Paylaş → Ana Ekrana Ekle ile siteyi ekleyin; sonra ana ekrandaki simgeden açıp buradan açın.",
  denied: "Bildirim izni reddedilmiş. Tarayıcı ayarlarından bu siteye bildirim izni verin.",
  off: "Açınca hatırlatmalar bu cihaza anında gelir.",
  on: "Bu cihaza anlık bildirim gönderiliyor.",
};

type SettingsChange = { reminders_enabled?: boolean; email?: string; email_notifications?: boolean };

export function NotificationSettingsCard() {
  const { me, setMe } = useSession();
  const toast = useToast();
  const state = useAsync(() => api.notificationSettings(), []);
  const [email, setEmail] = useState("");
  const [push, setPush] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (state.data) setEmail(state.data.email ?? "");
  }, [state.data]);

  useEffect(() => {
    readPushState().then(setPush, () => setPush("unsupported"));
  }, []);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
    } catch (cause: unknown) {
      toast(errorMessage(cause, cause instanceof Error ? cause.message : undefined), "danger");
    } finally {
      setBusy(false);
    }
  };

  const save = (changes: SettingsChange, message: string) =>
    run(async () => {
      const next = await api.updateNotificationSettings(changes);
      if (changes.reminders_enabled !== undefined) {
        setMe({ ...me, reminders_enabled: next.reminders_enabled });
      }
      state.reload();
      toast(message);
    });

  const togglePush = (enabled: boolean) =>
    run(async () => {
      if (enabled && state.data) {
        await enablePush(state.data.push_public_key);
        toast("Bu cihazda anlık bildirimler açıldı.");
      } else {
        await disablePush();
        toast("Bu cihazda anlık bildirimler kapatıldı.");
      }
      setPush(await readPushState());
    });

  const sendTest = () =>
    run(async () => {
      const result = await api.testNotification();
      const parts = ["Deneme bildirimi oluşturuldu."];
      if (result.push_devices) {
        parts.push(`${result.push_sent}/${result.push_devices} cihaza anlık bildirim gönderildi.`);
      }
      if (result.email === "sent") parts.push("E-posta gönderildi.");
      if (result.email === "failed") parts.push("E-posta gönderilemedi; eklenti günlüğüne bakın.");
      toast(parts.join(" "), result.email === "failed" ? "danger" : "success");
      window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED_EVENT));
    });

  if (state.error) {
    return (
      <Card title="Bildirimler">
        <ErrorNote message={state.error} onRetry={state.reload} />
      </Card>
    );
  }
  if (!state.data) {
    return (
      <Card title="Bildirimler">
        <Loading />
      </Card>
    );
  }

  const data = state.data;
  const hour = `${String(data.reminder_hour).padStart(2, "0")}:00`;
  const pushBlocked = push === null || push === "unsupported" || push === "needs-install" || push === "denied";

  return (
    <Card
      title="Bildirimler"
      action={
        <button type="button" className="btn ghost sm" disabled={busy} onClick={() => void sendTest()}>
          <Icon name="bell" size={16} />
          Deneme gönder
        </button>
      }
    >
      <div className="stack">
        <Toggle
          checked={data.reminders_enabled}
          disabled={busy}
          onChange={(value) =>
            void save({ reminders_enabled: value }, value ? "Hatırlatmalar açıldı." : "Hatırlatmalar kapatıldı.")
          }
          label="Hatırlatmalar"
          hint={`Ekstre kesimi, son ödeme, bütçe ve kart limiti uyarıları her gün ${hour}'da oluşturulur.`}
        />
        <div className="divider" />
        <Toggle
          checked={push === "on"}
          disabled={busy || pushBlocked}
          onChange={(value) => void togglePush(value)}
          label="Bu cihazda anlık bildirim"
          hint={push ? PUSH_HINTS[push] : "Denetleniyor…"}
        />
        <div className="divider" />
        {data.email_available ? (
          <>
            <Field label="E-posta adresi" group>
              <div className="row">
                <input
                  className="input"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  placeholder="ornek@gmail.com"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
                {email.trim() !== (data.email ?? "") && (
                  <button
                    type="button"
                    className="btn secondary"
                    disabled={busy}
                    onClick={() => void save({ email: email.trim() }, "E-posta adresi kaydedildi.")}
                  >
                    Kaydet
                  </button>
                )}
              </div>
            </Field>
            <Toggle
              checked={data.email_notifications}
              disabled={busy || !data.email}
              onChange={(value) =>
                void save(
                  { email_notifications: value },
                  value ? "E-posta bildirimleri açıldı." : "E-posta bildirimleri kapatıldı.",
                )
              }
              label="E-postayla da gönder"
              hint={data.email ? undefined : "Önce e-posta adresinizi kaydedin."}
            />
          </>
        ) : (
          <p className="muted small">
            E-postayla bildirim için yöneticinin eklenti ayarlarında e-posta sunucusunu (SMTP) tanımlaması
            gerekir.
          </p>
        )}
      </div>
    </Card>
  );
}
