import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { useSearchParams } from "react-router-dom";
import { BottomSheet } from "../components/BottomSheet";
import { Calendar } from "../components/Calendar";
import { FilterPanel } from "../components/FilterPanel";
import { ArticleCard } from "../components/ArticleCard";
import { CalendarIcon, CloseIcon, SlidersIcon } from "../components/Icons";
import { useArticles } from "../hooks/useArticles";
import { useFavorites } from "../hooks/useFavorites";
import { levelMeta, LEVEL_ORDER } from "../lib/levels";
import { isConfigured, configMissingMessage } from "../lib/supabase";
import type { Filters } from "../types";

const EMPTY_FILTERS: Filters = { themes: [], levels: [], styles: [] };

export function HomePage() {
  const { articles, loading, error, reload } = useArticles();
  const { isFavorite, toggle } = useFavorites();
  const [params, setParams] = useSearchParams();

  const [calendarOpen, setCalendarOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const selectedDate = params.get("date");

  const setSelectedDate = (date: string | null) => {
    const next = new URLSearchParams(params);
    if (date) next.set("date", date);
    else next.delete("date");
    setParams(next, { replace: true });
  };

  const available = useMemo(() => {
    const themes = new Set<string>();
    const levels = new Set<string>();
    const styles = new Set<string>();
    for (const a of articles) {
      themes.add(a.theme);
      levels.add(a.level);
      styles.add(a.style);
    }
    return {
      themes: [...themes].sort(),
      levels: [...levels].sort(),
      styles: [...styles].sort(),
    };
  }, [articles]);

  /** 只标记有文章的日期（PRD §2.1）。 */
  const activeDates = useMemo(() => {
    const set = new Set<string>();
    for (const a of articles) set.add(a.publish_date);
    return set;
  }, [articles]);

  const filtered = useMemo(() => {
    return articles.filter((a) => {
      if (selectedDate && a.publish_date !== selectedDate) return false;
      if (filters.themes.length && !filters.themes.includes(a.theme)) return false;
      if (filters.levels.length && !filters.levels.includes(a.level)) return false;
      if (filters.styles.length && !filters.styles.includes(a.style)) return false;
      return true;
    });
  }, [articles, selectedDate, filters]);

  useEffect(() => {
    document.title = "英语泛读 · 首页";
  }, []);

  const toggleLevel = (level: string) => {
    setFilters((prev) => ({
      ...prev,
      levels: prev.levels.includes(level)
        ? prev.levels.filter((v) => v !== level)
        : [...prev.levels, level],
    }));
  };

  const activeFilterCount =
    filters.themes.length + filters.levels.length + filters.styles.length;

  const clearFilters = () => {
    setFilters(EMPTY_FILTERS);
    setSelectedDate(null);
  };

  return (
    <div className="home">
      {/* 难度是学生最常用的筛选，常驻一行，点一下就换 */}
      <div className="quickbar">
        <div className="quickbar-scroll">
          <button
            type="button"
            className={`chip${filters.levels.length === 0 ? " is-active" : ""}`}
            onClick={() => setFilters((prev) => ({ ...prev, levels: [] }))}
            aria-pressed={filters.levels.length === 0}
          >
            全部
          </button>

          {LEVEL_ORDER.map((level) => {
            const meta = levelMeta(level);
            const active = filters.levels.includes(level);
            return (
              <button
                type="button"
                key={level}
                className={`chip chip-level${active ? " is-active" : ""}`}
                style={
                  {
                    "--lvl": `var(--${meta.tone})`,
                    "--lvl-wash": `var(--${meta.tone}-wash)`,
                  } as CSSProperties
                }
                onClick={() => toggleLevel(level)}
                aria-pressed={active}
              >
                <span className="chip-dot" aria-hidden="true" />
                {meta.short} {meta.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="toolbar">
        <button
          type="button"
          className={`tool-btn${calendarOpen ? " is-active" : ""}`}
          onClick={() => setCalendarOpen((v) => !v)}
          aria-expanded={calendarOpen}
        >
          <CalendarIcon />
          日历
        </button>
        <button
          type="button"
          className={`tool-btn${filterOpen ? " is-active" : ""}`}
          onClick={() => setFilterOpen((v) => !v)}
          aria-expanded={filterOpen}
        >
          <SlidersIcon />
          筛选
          {activeFilterCount > 0 ? ` (${activeFilterCount})` : ""}
        </button>

        {selectedDate ? (
          <span className="date-pill">
            {selectedDate}
            <button
              type="button"
              onClick={() => setSelectedDate(null)}
              aria-label="清除日期筛选"
            >
              <CloseIcon />
            </button>
          </span>
        ) : null}

        <button type="button" className="link-btn tool-refresh" onClick={() => void reload()}>
          刷新
        </button>

        <span className="tool-count">{filtered.length} 篇</span>
      </div>

      {!isConfigured ? <div className="notice notice-warn">{configMissingMessage}</div> : null}

      {loading ? <div className="state">正在取文章…</div> : null}

      {error ? (
        <div className="notice notice-err">
          读取失败：{error}
          <button type="button" className="link-btn" onClick={() => void reload()}>
            重试
          </button>
        </div>
      ) : null}

      {!loading && !error && filtered.length === 0 ? (
        <div className="state">
          {articles.length === 0 ? (
            <>
              <p className="state-title">还没有发布文章</p>
              <p className="state-text">文章发布后会自动出现在这里。</p>
            </>
          ) : (
            <>
              <p className="state-title">这个条件下没有文章</p>
              <p className="state-text">放宽一点难度或主题就能找到。</p>
              <button type="button" className="link-btn" onClick={clearFilters}>
                清空筛选
              </button>
            </>
          )}
        </div>
      ) : null}

      <div className="card-list">
        {filtered.map((article) => (
          <ArticleCard
            key={article.id}
            article={article}
            favorite={isFavorite(article.id)}
            onToggleFavorite={toggle}
          />
        ))}
      </div>

      <BottomSheet
        open={calendarOpen}
        title="按日期找文章"
        onClose={() => setCalendarOpen(false)}
      >
        <Calendar
          activeDates={activeDates}
          selectedDate={selectedDate}
          onSelectDate={(date) => {
            setSelectedDate(date);
            setCalendarOpen(false);
          }}
        />
      </BottomSheet>

      <BottomSheet open={filterOpen} title="筛选" onClose={() => setFilterOpen(false)}>
        <FilterPanel
          filters={filters}
          onChange={setFilters}
          available={available}
          resultCount={filtered.length}
          totalCount={articles.length}
        />
      </BottomSheet>
    </div>
  );
}
