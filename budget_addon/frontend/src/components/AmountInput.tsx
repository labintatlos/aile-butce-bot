import { sanitiseAmount } from "../format";

interface Props {
  value: string;
  onChange: (value: string) => void;
}

/**
 * Tutar alanı.
 *
 * `inputMode="decimal"` mobilde sayı klavyesini açar. Doğrulama ve kuruşa
 * çevirme sunucuda yapılır; burada yalnızca kullanıcının yanlış karakter
 * yazması engellenir.
 */
export function AmountInput({ value, onChange }: Props) {
  return (
    <label className="field">
      <span className="label">Tutar</span>
      <div className="amount-row">
        <input
          className="control amount"
          type="text"
          inputMode="decimal"
          autoComplete="off"
          placeholder="0,00"
          value={value}
          onChange={(event) => onChange(sanitiseAmount(event.target.value))}
        />
        <span className="currency">TL</span>
      </div>
    </label>
  );
}
