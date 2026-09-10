/**
 * İlk yönetici kurulumu.
 *
 * Sitede henüz giriş yapabilen bir yönetici yokken giriş ekranı yerine
 * gösterilir. Önce eklenti günlüğüne yazılan kurulum kodu istenir: adresi
 * bulan biri kodu bilmeden yönetici olamaz.
 */

import { useState, type FormEvent } from "react";

import { api, type SetupPerson } from "../api";
import { Icon } from "../components/icons";
import { Field } from "../components/ui";
import { errorMessage } from "../hooks";

const NEW_PERSON = "new";

export function Setup({ onSuccess }: { onSuccess: () => void }) {
  const [code, setCode] = useState("");
  const [people, setPeople] = useState<SetupPerson[] | null>(null);
  const [personId, setPersonId] = useState(NEW_PERSON);
  const [displayName, setDisplayName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const verify = async (event: FormEvent) => {
    event.preventDefault();
    if (!code.trim()) return setError("Kurulum kodunu girin.");
    setBusy(true);
    setError(null);
    try {
      const found = await api.verifySetup(code.trim());
      setPeople(found);
      setPersonId(found.length ? String(found[0].id) : NEW_PERSON);
    } catch (cause: unknown) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  const complete = async (event: FormEvent) => {
    event.preventDefault();
    const isNew = personId === NEW_PERSON;
    if (isNew && !displayName.trim()) return setError("Adınızı yazın.");
    if (!username.trim()) return setError("Bir kullanıcı adı belirleyin.");
    if (password.length < 8) return setError("Şifre en az 8 karakter olmalıdır.");
    if (password !== repeat) return setError("Şifreler aynı değil.");
    setBusy(true);
    setError(null);
    try {
      await api.completeSetup({
        code: code.trim(),
        user_id: isNew ? null : Number(personId),
        display_name: isNew ? displayName.trim() : null,
        username: username.trim(),
        password,
      });
      onSuccess();
    } catch (cause: unknown) {
      setError(errorMessage(cause));
      setBusy(false);
    }
  };

  return (
    <div className="auth">
      <div className="auth-panel">
        <div className="brand">
          <span className="brand-mark">
            <Icon name="wallet" size={20} />
          </span>
          Aile Bütçe
        </div>

        <h1>İlk kurulum</h1>

        {people === null ? (
          <>
            <p className="muted">
              Sitede henüz yönetici yok. Home Assistant'ta eklentinin <strong>Günlük</strong>{" "}
              sekmesinde yazan kurulum kodunu girin.
            </p>
            <form className="stack" onSubmit={verify} noValidate>
              <Field label="Kurulum kodu" hint="Örnek: 1234-5678">
                <input
                  className="input"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  autoFocus
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                />
              </Field>
              {error && (
                <div className="alert danger" role="alert">
                  {error}
                </div>
              )}
              <button className="btn primary lg block" type="submit" disabled={busy}>
                {busy ? "Denetleniyor…" : "Devam et"}
              </button>
            </form>
          </>
        ) : (
          <>
            <p className="muted">
              Yönetici hesabınızı oluşturun. Diğer kişileri sonra <strong>Kişiler</strong> ekranından
              ekleyebilirsiniz.
            </p>
            <form className="stack" onSubmit={complete} noValidate>
              {people.length > 0 && (
                <Field label="Siz kimsiniz?" hint="Mevcut bir kişiyi seçerseniz geçmiş kayıtları sizde kalır.">
                  <select
                    className="select"
                    value={personId}
                    onChange={(event) => setPersonId(event.target.value)}
                  >
                    {people.map((person) => (
                      <option key={person.id} value={person.id}>
                        {person.display_name}
                      </option>
                    ))}
                    <option value={NEW_PERSON}>Yeni kişi</option>
                  </select>
                </Field>
              )}
              {personId === NEW_PERSON && (
                <Field label="Adınız">
                  <input
                    className="input"
                    autoComplete="name"
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                  />
                </Field>
              )}
              <Field label="Kullanıcı adı" hint="Türkçe karakter kullanmadan; harf, rakam, nokta veya tire.">
                <input
                  className="input"
                  autoComplete="username"
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                />
              </Field>
              <Field label="Şifre" hint="En az 8 karakter.">
                <input
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </Field>
              <Field label="Şifre (tekrar)">
                <input
                  className="input"
                  type="password"
                  autoComplete="new-password"
                  value={repeat}
                  onChange={(event) => setRepeat(event.target.value)}
                />
              </Field>
              {error && (
                <div className="alert danger" role="alert">
                  {error}
                </div>
              )}
              <button className="btn primary lg block" type="submit" disabled={busy}>
                {busy ? "Oluşturuluyor…" : "Hesabı oluştur"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
