import { useEffect } from "react";
import { Link } from "react-router-dom";
import { StarIcon } from "../components/Icons";
import { useFavorites } from "../hooks/useFavorites";
import { levelMeta } from "../lib/levels";
import type { CSSProperties } from "react";

/** 独立收藏页（PRD §2.5）：展示所有收藏文章，支持取消收藏。 */
export function FavoritesPage() {
  const { favorites, remove } = useFavorites();

  useEffect(() => {
    document.title = "我的收藏 · 英语泛读";
  }, []);

  return (
    <div className="home">
      <div className="page-head">
        <h1>我的收藏</h1>
        <p className="hint">
          收藏保存在这台设备的浏览器里（localStorage），不会上传云端。换浏览器或清空缓存后会丢失。
        </p>
      </div>

      {favorites.length === 0 ? (
        <div className="state">
          <p className="state-title">还没有收藏</p>
          <p className="state-text">读到喜欢的文章，点右上角的星星存起来。</p>
          <Link className="link-btn" to="/">
            去挑一篇文章
          </Link>
        </div>
      ) : (
        <>
          <div className="card-list">
            {favorites.map((item) => {
              const level = levelMeta(item.level);
              return (
                <article
                  className="card"
                  key={item.id}
                  style={{ "--tag": item.color_tag } as CSSProperties}
                >
                  <span className="card-spine" aria-hidden="true" />
                  <div className="card-body">
                    <div className="card-head">
                      <div className="card-titles">
                        <h3 className="card-title">
                          <Link to={`/read/${item.id}`}>{item.title_en}</Link>
                        </h3>
                        <p className="card-title-cn">{item.title_cn}</p>
                      </div>
                      <button
                        type="button"
                        className="fav-btn is-on"
                        onClick={() => remove(item.id)}
                        aria-label="取消收藏"
                        title="取消收藏"
                      >
                        <StarIcon />
                      </button>
                    </div>

                    <div className="card-tags">
                      <span className="tag tag-theme">{item.theme}</span>
                      <span className={`tag tag-level tag-${level.tone}`}>
                        {level.short} {level.label}
                      </span>
                      <span className="tag tag-plain">{item.style}</span>
                    </div>

                    <div className="card-foot">
                      <time dateTime={item.publish_date}>{item.publish_date}</time>
                      <span className="mono">
                        收藏于 {new Date(item.saved_at).toLocaleString("zh-CN")}
                      </span>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
