import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { fetchArticleById } from "../lib/articles";
import { useFavorites } from "../hooks/useFavorites";
import type { Article, ViewMode } from "../types";

const VIEW_OPTIONS: { key: ViewMode; label: string }[] = [
  { key: "en", label: "仅英文" },
  { key: "cn", label: "仅中文" },
  { key: "both", label: "双语同显" },
];

export function ReaderPage() {
  const { id = "" } = useParams<{ id: string }>();
  const [article, setArticle] = useState<Article | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<ViewMode>("both");

  /** 联动高亮：当前选中文本所在段落的下标 + 选区所在语言 */
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [activeSide, setActiveSide] = useState<"en" | "cn" | null>(null);

  const { isFavorite, toggle } = useFavorites();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchArticleById(id)
      .then((row) => {
        if (cancelled) return;
        if (!row) setError("文章不存在或未发布");
        setArticle(row);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    document.title = article ? `${article.title_en} · 英语泛读` : "英语泛读";
  }, [article]);

  /**
   * 鼠标选中一侧段落文本 -> 高亮绑定到另一侧的对应段落（PRD §2.4-4）。
   * english_paras 与 chinese_paras 按下标一一配对。
   */
  const handleSelect = useCallback(
    (index: number, side: "en" | "cn", container: HTMLElement) => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed) return;
      const text = selection.toString().trim();
      if (!text) return;
      const anchor = selection.anchorNode;
      if (!anchor || !container.contains(anchor)) return;
      setActiveIndex(index);
      setActiveSide(side);
    },
    [],
  );

  const clearHighlight = useCallback(() => {
    const selection = window.getSelection();
    if (!selection || selection.toString().trim() === "") {
      setActiveIndex(null);
      setActiveSide(null);
    }
  }, []);

  const pairs = useMemo(() => {
    if (!article) return [];
    const en = article.english_paras ?? [];
    const cn = article.chinese_paras ?? [];
    const len = Math.max(en.length, cn.length);
    return Array.from({ length: len }, (_, i) => ({
      index: i,
      en: en[i] ?? null,
      cn: cn[i] ?? null,
    }));
  }, [article]);

  if (loading) return <div className="page"><div className="state">加载中…</div></div>;
  if (error || !article) {
    return (
      <div className="page">
        <div className="notice err">{error ?? "文章不存在"}</div>
        <Link className="link-btn" to="/">
          ← 返回列表
        </Link>
      </div>
    );
  }

  const favorite = isFavorite(article.id);

  return (
    <div className="page reader">
      <div className="reader-top">
        <Link className="link-btn" to="/">
          ← 返回
        </Link>
        <button
          type="button"
          className={`fav-btn${favorite ? " on" : ""}`}
          onClick={() => toggle(article)}
          aria-pressed={favorite}
          title={favorite ? "取消收藏" : "收藏"}
        >
          {favorite ? "★" : "☆"} {favorite ? "已收藏" : "收藏"}
        </button>
      </div>

      <header className="reader-head">
        <h1>{article.title_en}</h1>
        <p className="title-cn">{article.title_cn}</p>
        <div className="card-tags">
          <span className="tag" style={{ backgroundColor: article.color_tag }}>
            {article.theme}
          </span>
          {article.sub_theme ? <span className="tag tag-plain">{article.sub_theme}</span> : null}
          <span className="tag level">{article.level}</span>
          <span className="tag tag-plain">{article.style}</span>
          <span className="tag tag-plain">{article.publish_date}</span>
        </div>
      </header>

      <div className="view-switch" role="group" aria-label="视图切换">
        {VIEW_OPTIONS.map((opt) => (
          <button
            type="button"
            key={opt.key}
            className={`view-btn${view === opt.key ? " active" : ""}`}
            onClick={() => setView(opt.key)}
            aria-pressed={view === opt.key}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <p className="reader-tip">选中任一段落中的文字，另一侧对应段落会自动高亮。</p>

      <article className="reader-body" onMouseUp={clearHighlight}>
        {pairs.map(({ index: i, en, cn }) => {
          const enActive = activeIndex === i && activeSide === "en";
          const cnActive = activeIndex === i && activeSide === "cn";
          // 选区在英文侧 -> 高亮中文对应段；反之亦然
          const enLinked = activeIndex === i && activeSide === "cn";
          const cnLinked = activeIndex === i && activeSide === "en";

          const cls = (side: "en" | "cn", active: boolean, linked: boolean) =>
            [
              side === "en" ? "para para-en" : "para para-cn",
              active ? "active" : "",
              linked ? "linked" : "",
            ]
              .filter(Boolean)
              .join(" ");

          return (
            <section className="para-pair" key={i}>
              {view !== "cn" && en ? (
                <p className={cls("en", enActive, enLinked)} onMouseUp={(e) => handleSelect(i, "en", e.currentTarget)}>
                  {en}
                </p>
              ) : null}

              {view !== "en" && cn ? (
                <p className={cls("cn", cnActive, cnLinked)} onMouseUp={(e) => handleSelect(i, "cn", e.currentTarget)}>
                  {cn}
                </p>
              ) : null}
            </section>
          );
        })}
      </article>

      <footer className="reader-foot">
        <Link className="link-btn" to="/">
          ← 返回文章列表
        </Link>
      </footer>
    </div>
  );
}
