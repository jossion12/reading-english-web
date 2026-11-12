import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { Link, useParams } from "react-router-dom";
import { BottomSheet } from "../components/BottomSheet";
import { FontPicker } from "../components/FontPicker";
import { ArrowLeftIcon, CalendarIcon, StarIcon, TypeIcon } from "../components/Icons";
import { fetchArticleById } from "../lib/articles";
import { levelMeta } from "../lib/levels";
import { useFavorites } from "../hooks/useFavorites";
import { useReadingProgress } from "../hooks/useReadingProgress";
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
  const [fontOpen, setFontOpen] = useState(false);

  /** 联动高亮：当前选中的一侧（index + 哪一边）+ 配对的那一段 */
  const [active, setActive] = useState<{ index: number; side: "en" | "cn" } | null>(null);

  const { isFavorite, toggle } = useFavorites();
  const progress = useReadingProgress([article?.id]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchArticleById(id)
      .then((row) => {
        if (cancelled) return;
        if (!row) setError("文章不存在或未发布");
        setArticle(row);
        window.scrollTo(0, 0);
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
   * 划词高亮：在英文侧选中文字，亮起配对的中文段（PRD §2.4-4）。
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
      setActive({ index, side });
    },
    [],
  );

  /**
   * 点一下就亮：手机上几乎没人会去划词，划词高亮等于没有。
   * 所以「点一段」是主交互，划词是桌面端的补充。
   */
  const handleTap = useCallback((index: number, side: "en" | "cn") => {
    // 正在划词时不要抢高亮，交给划词逻辑
    const selection = window.getSelection();
    if (selection && !selection.isCollapsed && selection.toString().trim()) return;

    // 再点同一段就是取消；点另一段则把高亮挪过去
    setActive((prev) =>
      prev && prev.index === index && prev.side === side ? null : { index, side },
    );
  }, []);

  const clearHighlight = useCallback(() => {
    const selection = window.getSelection();
    if (!selection || selection.toString().trim() === "") {
      setActive(null);
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

  const wordCount = useMemo(() => {
    if (!article) return 0;
    return (article.english_paras ?? [])
      .join(" ")
      .split(/\s+/)
      .filter(Boolean).length;
  }, [article]);

  if (loading) {
    return (
      <div className="reader">
        <div className="reader-bar" />
        <div className="reader-sheet">
          <div className="state">正在打开这篇文章…</div>
        </div>
      </div>
    );
  }

  if (error || !article) {
    return (
      <div className="reader">
        <header className="reader-bar">
          <Link to="/" className="reader-bar-back" aria-label="返回文章列表">
            <ArrowLeftIcon />
          </Link>
        </header>
        <div className="reader-sheet">
          <div className="notice notice-err">{error ?? "文章不存在"}</div>
          <Link to="/" className="link-btn">
            ← 返回文章列表
          </Link>
        </div>
      </div>
    );
  }

  const favorite = isFavorite(article.id);
  const level = levelMeta(article.level);

  const cls = (side: "en" | "cn", active: boolean, linked: boolean) =>
    [
      "para",
      side === "en" ? "para-en" : "para-cn",
      active ? "is-active" : "",
      linked ? "is-linked" : "",
    ]
      .filter(Boolean)
      .join(" ");

  return (
    <div className="reader">
      <div className="progress" aria-hidden="true">
        <div className="progress-fill" style={{ transform: `scaleX(${progress})` }} />
      </div>

      <header className="reader-bar">
        <Link to="/" className="reader-bar-back" aria-label="返回文章列表">
          <ArrowLeftIcon />
        </Link>
        <span className="reader-bar-title">{article.title_en}</span>
        <button
          type="button"
          className={`reader-bar-fav${favorite ? " is-on" : ""}`}
          onClick={() => toggle(article)}
          aria-pressed={favorite}
          aria-label={favorite ? "取消收藏" : "收藏"}
          title={favorite ? "取消收藏" : "收藏"}
        >
          <StarIcon />
        </button>
      </header>

      <article className="reader-sheet" style={{ "--tag": article.color_tag } as CSSProperties}>
        <div className="sheet-kicker">
          <span className="tag tag-theme">{article.theme}</span>
          {article.sub_theme ? <span className="tag tag-plain">{article.sub_theme}</span> : null}
          <span className={`tag tag-level tag-${level.tone}`}>
            {level.short} {level.label}
          </span>
          <span className="tag tag-plain">{article.style}</span>
        </div>

        <h1 className="reader-title">{article.title_en}</h1>
        <p className="reader-title-cn">{article.title_cn}</p>

        <div className="sheet-meta">
          <span>
            <CalendarIcon />
            {article.publish_date}
          </span>
          <span>{pairs.length} 段</span>
          <span>约 {wordCount} 词</span>
        </div>

        <div className="reader-controls">
          <div className="view-switch" role="group" aria-label="视图切换">
            {VIEW_OPTIONS.map((opt) => (
              <button
                type="button"
                key={opt.key}
                className={`view-btn${view === opt.key ? " is-active" : ""}`}
                onClick={() => setView(opt.key)}
                aria-pressed={view === opt.key}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <button type="button" className="tool-btn" onClick={() => setFontOpen(true)}>
            <TypeIcon />
            字体
          </button>

          <span className="reader-progress-text">已读 {Math.round(progress * 100)}%</span>
        </div>

        <p className="reader-tip">点一下任一段落，另一侧对应的段落会一起亮起来。</p>

        <div className="para-list" onMouseUp={clearHighlight}>
          {pairs.map(({ index: i, en, cn }) => {
            const enActive = active?.index === i && active.side === "en";
            const cnActive = active?.index === i && active.side === "cn";
            // 选区在英文侧 -> 高亮中文对应段；反之亦然
            const enLinked = active?.index === i && active.side === "cn";
            const cnLinked = active?.index === i && active.side === "en";

            return (
              <section className="para-pair" key={i}>
                <span className="para-no" aria-hidden="true">
                  {i + 1}
                </span>
                <div className="para-main">
                  {view !== "cn" && en ? (
                    <p
                      className={cls("en", enActive, enLinked)}
                      onMouseUp={(e) => handleSelect(i, "en", e.currentTarget)}
                      onClick={() => handleTap(i, "en")}
                    >
                      {en}
                    </p>
                  ) : null}

                  {view !== "en" && cn ? (
                    <p
                      className={cls("cn", cnActive, cnLinked)}
                      onMouseUp={(e) => handleSelect(i, "cn", e.currentTarget)}
                      onClick={() => handleTap(i, "cn")}
                    >
                      {cn}
                    </p>
                  ) : null}
                </div>
              </section>
            );
          })}
        </div>

        <footer className="reader-foot">
          <Link to="/" className="link-btn">
            ← 回到文章列表
          </Link>
          <Link to="/favorites" className="link-btn">
            我的收藏
          </Link>
        </footer>
      </article>

      <BottomSheet open={fontOpen} title="字体" onClose={() => setFontOpen(false)}>
        <FontPicker />
      </BottomSheet>
    </div>
  );
}
