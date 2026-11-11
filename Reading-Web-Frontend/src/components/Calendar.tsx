import { useMemo, useState } from "react";

interface CalendarProps {
  /** 有文章的日期集合，格式 YYYY-MM-DD */
  activeDates: Set<string>;
  /** 当前选中的日期 */
  selectedDate: string | null;
  onSelectDate: (date: string | null) => void;
}

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function toKey(year: number, month: number, day: number): string {
  return `${year}-${pad(month + 1)}-${pad(day)}`;
}

/** 周一为一周第一天。 */
function mondayFirstIndex(year: number, month: number): number {
  const jsDay = new Date(year, month, 1).getDay(); // 0=周日
  return (jsDay + 6) % 7;
}

export function Calendar({ activeDates, selectedDate, onSelectDate }: CalendarProps) {
  const today = useMemo(() => new Date(), []);
  const cursor = useMemo(
    () => ({ year: today.getFullYear(), month: today.getMonth() }),
    [today],
  );
  const [view, setView] = useState(cursor);

  const cells = useMemo(() => {
    const first = mondayFirstIndex(view.year, view.month);
    const daysInMonth = new Date(view.year, view.month + 1, 0).getDate();
    const list: (string | null)[] = [];
    for (let i = 0; i < first; i += 1) list.push(null);
    for (let d = 1; d <= daysInMonth; d += 1) list.push(toKey(view.year, view.month, d));
    while (list.length % 7 !== 0) list.push(null);
    return list;
  }, [view]);

  const shift = (delta: number) => {
    setView((prev) => {
      const next = new Date(prev.year, prev.month + delta, 1);
      return { year: next.getFullYear(), month: next.getMonth() };
    });
  };

  const todayKey = toKey(today.getFullYear(), today.getMonth(), today.getDate());

  return (
    <div className="calendar">
      <div className="calendar-head">
        <button type="button" className="icon-btn" onClick={() => shift(-1)} aria-label="上一月">
          ‹
        </button>
        <strong>
          {view.year} 年 {view.month + 1} 月
        </strong>
        <button type="button" className="icon-btn" onClick={() => shift(1)} aria-label="下一月">
          ›
        </button>
        {view.year !== today.getFullYear() || view.month !== today.getMonth() ? (
          <button type="button" className="link-btn" onClick={() => setView(cursor)}>
            回到本月
          </button>
        ) : null}
      </div>

      <div className="calendar-grid calendar-weekdays">
        {WEEKDAYS.map((w) => (
          <span key={w}>{w}</span>
        ))}
      </div>

      <div className="calendar-grid">
        {cells.map((key, idx) => {
          if (!key) return <span key={`empty-${idx}`} className="calendar-cell empty" />;
          const hasArticle = activeDates.has(key);
          const isSelected = key === selectedDate;
          const isToday = key === todayKey;
          return (
            <button
              type="button"
              key={key}
              className={[
                "calendar-cell",
                hasArticle ? "has-article" : "",
                isSelected ? "selected" : "",
                isToday ? "today" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={() => onSelectDate(isSelected ? null : key)}
              aria-pressed={isSelected}
              title={hasArticle ? `${key} 有文章` : key}
            >
              {Number(key.slice(-2))}
            </button>
          );
        })}
      </div>

      {selectedDate ? (
        <button type="button" className="link-btn calendar-clear" onClick={() => onSelectDate(null)}>
          清除日期筛选（{selectedDate}）
        </button>
      ) : (
        <p className="calendar-hint">圆点表示当天有文章，点击可选中。</p>
      )}
    </div>
  );
}
