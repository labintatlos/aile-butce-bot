/**
 * Kişiler: siteye kimin girebileceğini yalnızca yöneticiler yönetir.
 *
 * Kişi silinmez, devre dışı bırakılır: geçmiş harcamalar kimin girdiğini
 * göstermeye devam etmelidir. Kendi hesabını kapatmak veya kendi yönetici
 * yetkisini kaldırmak sunucuda da engellenir; burada o seçenekler hiç sunulmaz.
 */

import { useState, type FormEvent } from "react";

import { api, type AdminUser, type AdminUserInput } from "../api";
import { Icon } from "../components/icons";
import { Card, ErrorNote, Field, Loading, Modal, PageHeader, Toggle, useToast } from "../components/ui";
import { initialOf, useSession } from "../context";
import { errorMessage, useAsync } from "../hooks";

export function People() {
  const { me, refresh } = useSession();
  const toast = useToast();
  const state = useAsync(() => api.adminUsers(), []);
  const [editing, setEditing] = useState<AdminUser | "new" | null>(null);

  const saved = (message: string) => {
    setEditing(null);
    toast(message);
    state.reload();
    refresh().catch(() => undefined);
  };

  return (
    <>
      <PageHeader
        title="Kişiler"
        subtitle="Siteye kimlerin girebileceğini yönetin"
        actions={
          <button type="button" className="btn primary" onClick={() => setEditing("new")}>
            <Icon name="plus" size={18} />
            Kişi ekle
          </button>
        }
      />

      {state.error && <ErrorNote message={state.error} onRetry={state.reload} />}
      {!state.data && state.loading && <Loading />}

      {state.data && (
        <Card flush>
          <div className="list">
            {state.data.map((person) => (
              <button
                key={person.id}
                type="button"
                className="list-item"
                onClick={() => setEditing(person)}
              >
                <span className="avatar">{initialOf(person.display_name)}</span>
                <span className="list-main">
                  <span className="list-title">
                    {person.display_name}
                    {person.id === me.id ? " (siz)" : ""}
                  </span>
                  <span className="list-sub">
                    {person.username ? `@${person.username}` : "Giriş tanımlı değil"}
                  </span>
                </span>
                {person.is_admin && <span className="badge">Yönetici</span>}
                {!person.is_active && <span className="badge danger">Devre dışı</span>}
                <Icon name="chevronRight" size={18} />
              </button>
            ))}
          </div>
        </Card>
      )}

      {editing && (
        <PersonForm
          person={editing === "new" ? null : editing}
          isSelf={editing !== "new" && editing.id === me.id}
          onClose={() => setEditing(null)}
          onSaved={saved}
        />
      )}
    </>
  );
}

function PersonForm({
  person,
  isSelf,
  onClose,
  onSaved,
}: {
  person: AdminUser | null;
  isSelf: boolean;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [displayName, setDisplayName] = useState(person?.display_name ?? "");
  const [username, setUsername] = useState(person?.username ?? "");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(person?.is_admin ?? false);
  const [isActive, setIsActive] = useState(person?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needsPassword = !person || !person.has_login;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!displayName.trim()) return setError("İsim boş bırakılamaz.");
    if (!username.trim()) return setError("Kullanıcı adı gerekli.");
    if (needsPassword && !password) return setError("Bu kişi için bir şifre belirleyin.");
    if (password && password.length < 8) return setError("Şifre en az 8 karakter olmalıdır.");

    setBusy(true);
    setError(null);
    try {
      if (!person) {
        await api.addUser({
          display_name: displayName.trim(),
          username: username.trim(),
          password,
          is_admin: isAdmin,
        });
        onSaved(`${displayName.trim()} eklendi.`);
        return;
      }
      const changes: Partial<AdminUserInput> = {};
      if (displayName.trim() !== person.display_name) changes.display_name = displayName.trim();
      if (username.trim().toLowerCase() !== person.username) changes.username = username.trim();
      if (password) changes.password = password;
      if (isAdmin !== person.is_admin) changes.is_admin = isAdmin;
      if (isActive !== person.is_active) changes.is_active = isActive;
      await api.updateUser(person.id, changes);
      onSaved(password ? "Kaydedildi. Bu kişinin açık oturumları kapatıldı." : "Kaydedildi.");
    } catch (cause: unknown) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={person ? person.display_name : "Kişi ekle"}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            Vazgeç
          </button>
          <button type="submit" form="person-form" className="btn primary" disabled={busy}>
            {busy ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </>
      }
    >
      <form id="person-form" className="stack" onSubmit={submit} noValidate>
        <Field label="İsim">
          <input
            className="input"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
          />
        </Field>
        <Field label="Kullanıcı adı" hint="Türkçe karakter kullanmadan; harf, rakam, nokta veya tire.">
          <input
            className="input"
            autoComplete="off"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </Field>
        <Field
          label={needsPassword ? "Şifre" : "Yeni şifre"}
          hint={needsPassword ? "En az 8 karakter." : "Değiştirmek istemiyorsanız boş bırakın."}
        >
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </Field>
        <Toggle
          checked={isAdmin}
          disabled={isSelf}
          onChange={setIsAdmin}
          label="Yönetici"
          hint={isSelf ? "Kendi yönetici yetkinizi kaldıramazsınız." : "Kişileri ve şifreleri yönetebilir."}
        />
        {person && (
          <Toggle
            checked={isActive}
            disabled={isSelf}
            onChange={setIsActive}
            label="Siteye girebilir"
            hint={
              isSelf
                ? "Kendi hesabınızı kapatamazsınız."
                : "Kapatılırsa giriş yapamaz; geçmiş kayıtları silinmez."
            }
          />
        )}
        {error && (
          <div className="alert danger" role="alert">
            {error}
          </div>
        )}
      </form>
    </Modal>
  );
}
