/** 与 Supabase articles 表一一对应（只读）。 */
export interface Article {
  id: string;
  publish_date: string;
  title_en: string;
  title_cn: string;
  level: "L1" | "L2" | "L3";
  theme: string;
  sub_theme: string | null;
  style: string;
  color_tag: string;
  english_paras: string[];
  chinese_paras: string[];
  sort: number;
  is_published: boolean;
  source_id: string | null;
}

/** 收藏快照：存 localStorage，即使文章下架也能在收藏页看到。 */
export interface FavoriteItem {
  id: string;
  title_en: string;
  title_cn: string;
  theme: string;
  level: Article["level"];
  style: string;
  color_tag: string;
  publish_date: string;
  saved_at: string;
}

/** 阅读视图三档（PRD §2.4-2）。 */
export type ViewMode = "en" | "cn" | "both";

/** 筛选条件（PRD §2.2）。 */
export interface Filters {
  themes: string[];
  levels: string[];
  styles: string[];
}
