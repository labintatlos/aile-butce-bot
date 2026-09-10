/**
 * Telefondaki "Menü" sekmesi: alt çubuğa sığmayan sayfalar ve çıkış.
 */

import { Icon, type IconName } from "../components/icons";
import { Card, PageHeader } from "../components/ui";
import { authSourceLabel, initialOf, useSession } from "../context";
import type { Route } from "../hooks";

const ITEMS: readonly {
  route: Route;
  label: string;
  hint: string;
  icon: IconName;
  admin?: boolean;
}[] = [
  { route: "gelirler", label: "Gelirler", hint: "Maaş ve diğer gelirler", icon: "income" },
  { route: "sabit", label: "Sabit giderler", hint: "Kira, aidat, abonelikler", icon: "repeat" },
  { route: "ayarlar", label: "Ayarlar", hint: "Kartlar, kategoriler ve hesap", icon: "settings" },
  { route: "kisiler", label: "Kişiler", hint: "Giriş, şifre ve yönetici yetkisi", icon: "users", admin: true },
];

export function More() {
  const { me, navigate, logout } = useSession();

  return (
    <>
      <PageHeader title="Menü" />
      <div className="stack">
        <Card flush>
          <div className="list">
            <div className="list-item">
              <span className="avatar">{initialOf(me.display_name)}</span>
              <span className="list-main">
                <span className="list-title">{me.display_name}</span>
                <span className="list-sub">
                  {me.username ? `@${me.username} · ` : ""}
                  {authSourceLabel(me.auth_source)}
                </span>
              </span>
            </div>
          </div>
        </Card>

        <Card flush>
          <div className="list">
            {ITEMS.filter((item) => !item.admin || me.is_admin).map((item) => (
              <button
                key={item.route}
                type="button"
                className="list-item"
                onClick={() => navigate(item.route)}
              >
                <span className="list-icon">
                  <Icon name={item.icon} size={18} />
                </span>
                <span className="list-main">
                  <span className="list-title">{item.label}</span>
                  <span className="list-sub">{item.hint}</span>
                </span>
                <Icon name="chevronRight" size={18} />
              </button>
            ))}
          </div>
        </Card>

        {me.auth_source === "session" && (
          <button type="button" className="btn danger-ghost block" onClick={() => void logout()}>
            <Icon name="logout" size={18} />
            Çıkış yap
          </button>
        )}
      </div>
    </>
  );
}
