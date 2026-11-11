import { Link } from "react-router-dom";
import type { Article } from "../types";

interface ArticleCardProps {
  article: Article;
  favorite: boolean;
  onToggleFavorite: (article: Article) => void;
}

/** 难度标签配色，与后台配置无关的固定语义色。 */
const LEVEL_CLASS: Record<string, string> = {
  L1: "level-l1",
  L2: "level-l2",
  L3: "level-l3",
};

export function ArticleCard({ article, favorite, onToggleFavorite }: ArticleCardProps) {
  return (
    <article className="card">
      <div className="card-top">
        <div className="card-titles">
          <h3>
            <Link to={`/read/${article.id}`}>{article.title_en}</Link>
          </h3>
          <p className="title-cn">{article.title_cn}</p>
        </div>
        <button
          type="button"
          className={`fav-btn${favorite ? " on" : ""}`}
          onClick={() => onToggleFavorite(article)}
          aria-pressed={favorite}
          title={favorite ? "取消收藏" : "收藏"}
          aria-label={favorite ? "取消收藏" : "收藏"}
        >
          {favorite ? "★" : "☆"}
        </button>
      </div>

      <div className="card-tags">
        <span className="tag" style={{ backgroundColor: article.color_tag }}>
          {article.theme}
        </span>
        {article.sub_theme ? (
          <span className="tag tag-plain">{article.sub_theme}</span>
        ) : null}
        <span className={`tag level ${LEVEL_CLASS[article.level] ?? ""}`}>{article.level}</span>
        <span className="tag tag-plain">{article.style}</span>
      </div>

      <div className="card-foot">
        <time dateTime={article.publish_date}>{article.publish_date}</time>
        <Link className="read-link" to={`/read/${article.id}`}>
          开始阅读 →
        </Link>
      </div>
    </article>
  );
}
