/** 文章列表加载：一次取全量已发布文章，供日历 / 筛选 / 列表共用。 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchPublishedArticles } from "../lib/articles";
import type { Article } from "../types";

export interface UseArticlesResult {
  articles: Article[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
}

export function useArticles(): UseArticlesResult {
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // 后台 Supabase 增强可能在组件卸载后才回来，别再 setState
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchPublishedArticles((fresh) => {
        if (alive.current) setArticles(fresh);
      });
      if (alive.current) setArticles(rows);
    } catch (err) {
      if (alive.current) setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return useMemo(
    () => ({ articles, loading, error, reload }),
    [articles, loading, error, reload],
  );
}
