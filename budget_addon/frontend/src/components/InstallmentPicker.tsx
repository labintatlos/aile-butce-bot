import { installmentLabel } from "../format";

interface Props {
  value: number;
  max: number;
  disabled: boolean;
  onChange: (value: number) => void;
}

/**
 * Taksit seçimi.
 *
 * Nakit ödemede devre dışıdır ve değer 1'e sabitlenir (§8). Devre dışıyken
 * sebebi de yazılır; sessizce kilitlenen bir alan kullanıcıyı şaşırtır.
 */
export function InstallmentPicker({ value, max, disabled, onChange }: Props) {
  const options = Array.from({ length: max }, (_, index) => index + 1);

  return (
    <div className="field">
      <span className="label">Taksit</span>
      {disabled ? (
        <p className="hint">Nakit ödemede taksit yapılamaz.</p>
      ) : (
        <div className="chips">
          {options.map((count) => (
            <button
              key={count}
              type="button"
              className={`chip ${count === value ? "chip-active" : ""}`}
              onClick={() => onChange(count)}
            >
              {installmentLabel(count)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
