import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import { ArrowRightIcon, StarIcon } from "./Icons";
import { levelMeta } from "../lib/levels";
import type { Article } from "../types";

interface ArticleCardProps {
  article: Article;
  favorite: boolean;
  onToggleFavorite: (article: Article) => void;
}

/**
 * 文章卡片。
 *
 * 左侧一条主题色「书脊」把这篇文章的主题色带到眼前，标题用所选的英文字体渲染，
 * 难度徽标同时写代号和说法（L2 中等）—— 学生看的是「中等」，老师看的是「L2」。
 */
export function ArticleCard({ article, favorite, onToggleFavorite }: ArticleCardProps) {
  const level = levelMeta(article.level);

  return (
    <article className="card" style={{ "--tag": article.color_tag } as CSSProperties}>
      <span className="card-spine" aria-hidden="true" />
      <div className="card-body">
        <div className="card-head">
          <div className="card-titles">
            <h3 className="card-title">
              <Link to={`/read/${article.id}`}>{article.title_en}</Link>
            </h3>
            <p className="card-title-cn">{article.title_cn}</p>
          </div>

          <button
            type="button"
            className={`fav-btn${favorite ? " is-on" : ""}`}
            onClick={() => onToggleFavorite(article)}
            aria-pressed={favorite}
            title={favorite ? "取消收藏" : "收藏"}
            aria-label={favorite ? "取消收藏" : "收藏"}
          >
            <StarIcon />
          </button>
        </div>

        <div className="card-tags">
          <span className="tag tag-theme">{article.theme}</span>
          {article.sub_theme ? <span className="tag tag-plain">{article.sub_theme}</span> : null}
          <span className={`tag tag-level tag-${level.tone}`}>
            {level.short} {level.label}
          </span>
          <span className="tag tag-plain">{article.style}</span>
        </div>

        <div className="card-foot">
          <time dateTime={article.publish_date}>{article.publish_date}</time>
          <Link className="card-go" to={`/read/${article.id}`}>
            开始阅读
            <ArrowRightIcon />
          </Link>
        </div>
      </div>
    </article>
  );
}
