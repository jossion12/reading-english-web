import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
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
  const {
    dates,
    articles,
    loading,
    loadingMore,
    error,
    moreError,
    hasMore,
    reload,
    loadMore,
    ensureDate,
  } = useArticles();
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
    // 日历可能选到「还没滚动加载到」的更早日期，先把它补拉回来
    if (date) void ensureDate(date);
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

  /** 只标记有文章的日期（PRD §2.1）。日期来自完整 index，不受「只加载了部分分片」影响。 */
  const activeDates = useMemo(() => new Set(dates), [dates]);

  const filtered = useMemo(() => {
    return articles.filter((a) => {
      if (selectedDate && a.publish_date !== selectedDate) return false;
      if (filters.themes.length && !filters.themes.includes(a.theme)) return false;
      if (filters.levels.length && !filters.levels.includes(a.level)) return false;
      if (filters.styles.length && !filters.styles.includes(a.style)) return false;
      return true;
    });
  }, [articles, selectedDate, filters]);

  // 列表底部哨兵：只有「用户滚动过」之后进入视口才加载下一个更早日期的分片。
  // 首屏首次渲染时哨兵可能因内容不足一屏而可见，此时绝不自动加载 —— 严格保证
  // 首屏只请求今日数据（加载时效）。筛选/选中日期时也不自动加载。
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const hasScrolled = useRef(false);
  const canAutoLoad = !selectedDate && activeFilterCount(filters) === 0 && !loading && !error;

  useEffect(() => {
    const onScroll = () => {
      if (window.scrollY > 40) hasScrolled.current = true;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || !hasMore || !canAutoLoad) return;
    const io = new IntersectionObserver(
      (entries) => {
        // 没滚动过就不触发：避免首屏内容不足一屏时连锁预加载多天
        if (hasScrolled.current && entries.some((e) => e.isIntersecting)) void loadMore();
      },
      { rootMargin: "0px" },
    );
    io.observe(node);
    return () => io.disconnect();
  }, [hasMore, canAutoLoad, loadMore]);

  useEffect(() => {
    document.title = "英语泛读 · 首页";
  }, []);

  // 深链带 ?date= 时，确保该日期分片已加载
  useEffect(() => {
    if (selectedDate) void ensureDate(selectedDate);
  }, [selectedDate, ensureDate]);

  const toggleLevel = (level: string) => {
    setFilters((prev) => ({
      ...prev,
      levels: prev.levels.includes(level)
        ? prev.levels.filter((v) => v !== level)
        : [...prev.levels, level],
    }));
  };

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
          {activeFilterCount(filters) > 0 ? ` (${activeFilterCount(filters)})` : ""}
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

      {/* 滚动到底的加载哨兵 + 状态提示（仅在无筛选的浏览态出现） */}
      {canAutoLoad && filtered.length > 0 ? (
        <div ref={sentinelRef} className="load-sentinel" aria-live="polite">
          {loadingMore ? (
            <span className="load-more">正在加载更早的文章…</span>
          ) : moreError ? (
            <span className="load-more load-more-err">
              加载失败：{moreError}
              <button type="button" className="link-btn" onClick={() => void loadMore()}>
                重试
              </button>
            </span>
          ) : hasMore ? (
            <span className="load-more load-more-hint">
              向下滚动，阅读更早的文章
              <button type="button" className="link-btn load-more-btn" onClick={() => void loadMore()}>
                加载更多
              </button>
            </span>
          ) : (
            <span className="load-more load-more-end">— 已经到底啦 —</span>
          )}
        </div>
      ) : null}

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

/** 筛选是否处于激活态（抽成纯函数，供 IntersectionObserver 依赖判断）。 */
function activeFilterCount(filters: Filters): number {
  return filters.themes.length + filters.levels.length + filters.styles.length;
}
