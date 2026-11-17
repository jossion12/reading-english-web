/**
 * 文章渐进加载：首屏只取「最新一天」的分片，滚动到底才逐日加载更早数据。
 *
 * 状态分层：
 *   - dates   来自 index 的全部日期（倒序）—— 日历标记用，与加载进度无关
 *   - slices  已加载的日期分片 Map<date, Article[]>
 *   - articles 已加载文章按 dates 顺序扁平化 —— 整体 publish_date 倒序 / sort 升序
 *
 * 加载时机：
 *   - mount   → loadInitial()：拉 index，再取 dates[0]（最新一天）
 *   - 滚动底  → loadMore()：取下一个未加载日期
 *   - 日历选日期 → ensureDate(date)：该日期没加载过就补拉（可能与 loadMore 撞车，用 ref 串行）
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchArticleIndex, fetchDateSlice } from "../lib/articles";
import type { Article } from "../types";

export interface UseArticlesResult {
  /** 全部有文章的日期（倒序），供日历标记，即使对应分片还没加载 */
  dates: string[];
  /** 已加载文章，按时间倒序（publish_date desc, sort asc） */
  articles: Article[];
  /** 首屏加载中（index + 最新一天） */
  loading: boolean;
  /** 滚动加载更早日期中 */
  loadingMore: boolean;
  /** 首屏错误 */
  error: string | null;
  /** 加载更多失败（非阻塞，可重试） */
  moreError: string | null;
  /** 是否还有更早的日期没加载 */
  hasMore: boolean;
  /** 重新从 index 开始加载 */
  reload: () => Promise<void>;
  /** 加载下一个更早日期 */
  loadMore: () => Promise<void>;
  /** 确保某日期已加载（日历跳转到未加载日期时用） */
  ensureDate: (date: string) => Promise<void>;
}

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export function useArticles(): UseArticlesResult {
  const [dates, setDates] = useState<string[]>([]);
  const [slices, setSlices] = useState<Map<string, Article[]>>(new Map());
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [moreError, setMoreError] = useState<string | null>(null);

  // 组件卸载后不再 setState；loadSlice 串行化，避免 loadMore 与 ensureDate 重复拉同一天
  const alive = useRef(true);
  const loadingDates = useRef<Set<string>>(new Set());
  const datesRef = useRef<string[]>([]);
  const slicesRef = useRef<Map<string, Article[]>>(new Map());

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const syncRefs = useCallback((d: string[], s: Map<string, Article[]>) => {
    datesRef.current = d;
    slicesRef.current = s;
  }, []);

  /** 拉取单个日期分片并写入状态；已加载/加载中的日期直接跳过。 */
  const loadSlice = useCallback(
    async (date: string): Promise<boolean> => {
      if (!date || slicesRef.current.has(date) || loadingDates.current.has(date)) return false;
      loadingDates.current.add(date);
      try {
        const rows = await fetchDateSlice(date);
        if (!alive.current) return false;
        const next = new Map(slicesRef.current);
        next.set(date, rows);
        slicesRef.current = next;
        setSlices(next);
        return true;
      } finally {
        loadingDates.current.delete(date);
      }
    },
    [],
  );

  const loadInitial = useCallback(async () => {
    setLoading(true);
    setError(null);
    setMoreError(null);
    loadingDates.current.clear();
    try {
      const index = await fetchArticleIndex();
      if (!alive.current) return;
      setDates(index);
      syncRefs(index, new Map());
      if (index.length) await loadSlice(index[0]);
    } catch (err) {
      if (alive.current) setError(messageOf(err));
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [loadSlice, syncRefs]);

  const reload = useCallback(async () => {
    if (!alive.current) return;
    // 重置数据，再走完整首屏流程
    const empty = new Map<string, Article[]>();
    setSlices(empty);
    setDates([]);
    syncRefs([], empty);
    await loadInitial();
  }, [loadInitial, syncRefs]);

  const loadMore = useCallback(async () => {
    if (loadingMore || loading) return;
    // 找第一个还没加载的日期（dates 已倒序，从最新往更早找）
    const next = datesRef.current.find((d) => !slicesRef.current.has(d));
    if (!next) return;
    setLoadingMore(true);
    setMoreError(null);
    try {
      await loadSlice(next);
    } catch (err) {
      if (alive.current) setMoreError(messageOf(err));
    } finally {
      if (alive.current) setLoadingMore(false);
    }
  }, [loadSlice, loading, loadingMore]);

  const ensureDate = useCallback(
    async (date: string) => {
      if (!date || slicesRef.current.has(date)) return;
      try {
        await loadSlice(date);
      } catch (err) {
        if (alive.current) setMoreError(messageOf(err));
      }
    },
    [loadSlice],
  );

  useEffect(() => {
    void loadInitial();
  }, [loadInitial]);

  const articles = useMemo(() => {
    const out: Article[] = [];
    for (const date of dates) {
      const items = slices.get(date);
      if (items) out.push(...items);
    }
    return out;
  }, [dates, slices]);

  const hasMore = useMemo(() => dates.some((d) => !slices.has(d)), [dates, slices]);

  return useMemo(
    () => ({
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
    }),
    [dates, articles, loading, loadingMore, error, moreError, hasMore, reload, loadMore, ensureDate],
  );
}
