/** 文章列表加载：一次取全量已发布文章，供日历 / 筛选 / 列表共用。 */
import { useCallback, useEffect, useMemo, useState } from "react";
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

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchPublishedArticles();
      setArticles(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
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
