/**
 * 收藏：保存在浏览器 localStorage，不上传云端（PRD §2.5）。
 * 换浏览器或清空缓存后收藏数据会丢失。
 */
import type { Article, FavoriteItem } from "../types";

const STORAGE_KEY = "reading.favorites.v1";

function readAll(): FavoriteItem[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item): item is FavoriteItem =>
        !!item && typeof item.id === "string" && typeof item.title_en === "string",
    );
  } catch {
    return [];
  }
}

function writeAll(items: FavoriteItem[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    // 隐私模式 / 配额满：忽略，收藏仅本次会话有效
  }
}

export function loadFavorites(): FavoriteItem[] {
  return readAll();
}

export function saveFavorites(items: FavoriteItem[]): void {
  writeAll(items);
}

export function toFavorite(article: Article): FavoriteItem {
  return {
    id: article.id,
    title_en: article.title_en,
    title_cn: article.title_cn,
    theme: article.theme,
    level: article.level,
    style: article.style,
    color_tag: article.color_tag,
    publish_date: article.publish_date,
    saved_at: new Date().toISOString(),
  };
}

export function isFavorited(items: FavoriteItem[], id: string): boolean {
  return items.some((item) => item.id === id);
}

export function toggleFavorite(items: FavoriteItem[], article: Article): FavoriteItem[] {
  if (isFavorited(items, article.id)) {
    return items.filter((item) => item.id !== article.id);
  }
  return [toFavorite(article), ...items];
}
