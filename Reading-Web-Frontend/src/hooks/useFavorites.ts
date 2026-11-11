/** 收藏状态：localStorage 持久化。 */
import { useCallback, useEffect, useState } from "react";
import { loadFavorites, saveFavorites, toggleFavorite } from "../lib/favorites";
import type { Article, FavoriteItem } from "../types";

export interface UseFavoritesResult {
  favorites: FavoriteItem[];
  isFavorite: (id: string) => boolean;
  toggle: (article: Article) => void;
  remove: (id: string) => void;
}

export function useFavorites(): UseFavoritesResult {
  const [favorites, setFavorites] = useState<FavoriteItem[]>([]);

  useEffect(() => {
    setFavorites(loadFavorites());
  }, []);

  const toggle = useCallback((article: Article) => {
    setFavorites((prev) => {
      const next = toggleFavorite(prev, article);
      saveFavorites(next);
      return next;
    });
  }, []);

  const remove = useCallback((id: string) => {
    setFavorites((prev) => {
      const next = prev.filter((item) => item.id !== id);
      saveFavorites(next);
      return next;
    });
  }, []);

  const isFavorite = useCallback(
    (id: string) => favorites.some((item) => item.id === id),
    [favorites],
  );

  return { favorites, isFavorite, toggle, remove };
}
