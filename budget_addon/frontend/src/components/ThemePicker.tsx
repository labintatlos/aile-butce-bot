import { useId } from "react";
import { useTheme, type ThemePreference } from "../theme";
import { Icon, type IconName } from "./icons";

const OPTIONS: { value: ThemePreference; label: string; icon: IconName; hint: string }[] = [
  { value: "light", label: "Açık", icon: "sun", hint: "Aydınlık ve ferah" },
  { value: "dark", label: "Koyu", icon: "moon", hint: "Düşük ışıkta rahat" },
  { value: "system", label: "Cihaz", icon: "monitor", hint: "Cihaz ayarını izle" },
];

export function ThemePicker({ compact = false }: { compact?: boolean }) {
  const { preference, resolved, setPreference } = useTheme();
  const id = useId();
  if (compact) {
    return (
      <label className="theme-select" title="Görünüm temasını değiştir">
        <Icon name={OPTIONS.find((option) => option.value === preference)!.icon} size={17} />
        <span className="sr-only">Görünüm teması</span>
        <select value={preference} onChange={(event) => setPreference(event.target.value as ThemePreference)}>
          {OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
    );
  }
  return (
    <div>
      <fieldset className="theme-options" aria-describedby={`${id}-hint`}>
        <legend className="sr-only">Görünüm teması</legend>
        {OPTIONS.map((option) => (
          <label key={option.value} className={`theme-option ${preference === option.value ? "selected" : ""}`}>
            <input type="radio" name={id} value={option.value} checked={preference === option.value} onChange={() => setPreference(option.value)} />
            <span className={`theme-preview ${option.value}`} aria-hidden="true"><i /><i /><i /></span>
            <span className="theme-option-label"><Icon name={option.icon} size={16} />{option.label}</span>
            <small>{option.hint}</small>
          </label>
        ))}
      </fieldset>
      <p id={`${id}-hint`} className="theme-hint" aria-live="polite">
        {preference === "system" ? `Cihazınızın görünümü otomatik izleniyor. Şu an ${resolved === "dark" ? "koyu" : "açık"} tema etkin.` : `${preference === "dark" ? "Koyu" : "Açık"} tema etkin. Cihaz ayarı değişse de seçiminiz korunur.`}
        {" "}Tercihiniz bu tarayıcıda saklanır.
      </p>
    </div>
  );
}
