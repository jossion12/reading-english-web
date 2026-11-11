import type { Filters } from "../types";

interface FilterPanelProps {
  filters: Filters;
  onChange: (next: Filters) => void;
  available: { themes: string[]; levels: string[]; styles: string[] };
  resultCount: number;
  totalCount: number;
}

interface GroupProps {
  title: string;
  options: string[];
  selected: string[];
  onToggle: (value: string) => void;
}

function Group({ title, options, selected, onToggle }: GroupProps) {
  if (options.length === 0) return null;
  return (
    <div className="filter-group">
      <h4>{title}</h4>
      <div className="filter-options">
        {options.map((option) => {
          const active = selected.includes(option);
          return (
            <button
              type="button"
              key={option}
              className={`chip${active ? " active" : ""}`}
              onClick={() => onToggle(option)}
              aria-pressed={active}
            >
              {option}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function FilterPanel({
  filters,
  onChange,
  available,
  resultCount,
  totalCount,
}: FilterPanelProps) {
  const toggleIn = (key: keyof Filters, value: string) => {
    const current = filters[key];
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    onChange({ ...filters, [key]: next });
  };

  const hasAny = filters.themes.length + filters.levels.length + filters.styles.length > 0;

  return (
    <div className="filter-panel">
      <Group
        title="主题"
        options={available.themes}
        selected={filters.themes}
        onToggle={(v) => toggleIn("themes", v)}
      />
      <Group
        title="文体"
        options={available.styles}
        selected={filters.styles}
        onToggle={(v) => toggleIn("styles", v)}
      />
      <Group
        title="难度"
        options={available.levels}
        selected={filters.levels}
        onToggle={(v) => toggleIn("levels", v)}
      />

      <div className="filter-foot">
        <span className="filter-count">
          命中 {resultCount} / {totalCount} 篇
        </span>
        {hasAny ? (
          <button
            type="button"
            className="link-btn"
            onClick={() => onChange({ themes: [], levels: [], styles: [] })}
          >
            清空筛选
          </button>
        ) : null}
      </div>
    </div>
  );
}
