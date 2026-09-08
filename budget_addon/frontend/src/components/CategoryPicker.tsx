import type { Category } from "../api";

interface Props {
  categories: Category[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export function CategoryPicker({ categories, selectedId, onSelect }: Props) {
  return (
    <div className="field">
      <span className="label">Kategori</span>
      <div className="grid">
        {categories.map((category) => (
          <button
            key={category.id}
            type="button"
            className={`tile ${category.id === selectedId ? "tile-active" : ""}`}
            onClick={() => onSelect(category.id)}
          >
            <span className="tile-emoji">{category.emoji}</span>
            <span className="tile-name">{category.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
