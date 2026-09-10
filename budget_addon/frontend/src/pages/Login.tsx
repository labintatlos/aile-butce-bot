/**
 * Giriş ekranı.
 *
 * Yalnızca web sitesinde görünür. Home Assistant panelinde ve Telegram
 * içinde kimlik zaten bağlamdan geldiği için bu ekran atlanır.
 */

import { useState, type FormEvent } from "react";

import { api } from "../api";
import { Icon, type IconName } from "../components/icons";
import { Field } from "../components/ui";
import { errorMessage } from "../hooks";

const HIGHLIGHTS: readonly { icon: IconName; title: string; text: string }[] = [
  {
    icon: "card",
    title: "Taksit ve ekstreler",
    text: "Her taksitin hangi ekstreye düştüğü kendiliğinden hesaplanır.",
  },
  {
    icon: "chart",
    title: "Anlaşılır raporlar",
    text: "Ay sonu tahmini, bütçe hedefleri ve geçen yılla karşılaştırma.",
  },
  {
    icon: "users",
    title: "Ortak giderler",
    text: "Kimin kime ne kadar borçlu olduğu tek bakışta.",
  },
];

export function Login({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError("Kullanıcı adı ve şifre gerekli.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.login(username.trim(), password, remember);
      onSuccess();
    } catch (cause: unknown) {
      setError(errorMessage(cause, "Giriş yapılamadı. Bağlantınızı kontrol edin."));
      setPassword("");
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

        <h1>Tekrar hoş geldiniz</h1>
        <p className="muted">Devam etmek için hesabınıza giriş yapın.</p>

        <form className="stack" onSubmit={submit} noValidate>
          <Field label="Kullanıcı adı">
            <input
              className="input"
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              autoFocus
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </Field>

          <Field label="Şifre">
            <div className="input-wrap">
              <input
                className="input"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <button
                type="button"
                className="icon-btn input-addon"
                onClick={() => setShowPassword((value) => !value)}
                aria-label={showPassword ? "Şifreyi gizle" : "Şifreyi göster"}
              >
                <Icon name={showPassword ? "eyeOff" : "eye"} size={18} />
              </button>
            </div>
          </Field>

          <label className="check">
            <input
              type="checkbox"
              checked={remember}
              onChange={(event) => setRemember(event.target.checked)}
            />
            Beni hatırla
          </label>

          {error && (
            <div className="alert danger" role="alert">
              {error}
            </div>
          )}

          <button className="btn primary lg block" type="submit" disabled={busy}>
            {busy ? "Giriş yapılıyor…" : "Giriş yap"}
          </button>
        </form>
      </div>

      <aside className="auth-aside" aria-hidden="true">
        <h2>Ailenizin bütçesi, tek ve güvenli bir yerde.</h2>
        <ul>
          {HIGHLIGHTS.map((item) => (
            <li key={item.title}>
              <span>
                <Icon name={item.icon} size={18} />
              </span>
              <span>
                <strong>{item.title}</strong>
                <small>{item.text}</small>
              </span>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
