import type { PaymentMethod } from "../api";

interface Props {
  methods: PaymentMethod[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export function PaymentMethodPicker({ methods, selectedId, onSelect }: Props) {
  return (
    <div className="field">
      <span className="label">Ödeme Yöntemi</span>
      <div className="chips">
        {methods.map((method) => (
          <button
            key={method.id}
            type="button"
            className={`chip ${method.id === selectedId ? "chip-active" : ""}`}
            onClick={() => onSelect(method.id)}
          >
            {method.type === "cash" ? "💵" : "💳"} {method.name}
          </button>
        ))}
      </div>
    </div>
  );
}
