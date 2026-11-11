import { NavLink, Route, Routes } from "react-router-dom";
import { HomePage } from "./pages/HomePage";
import { ReaderPage } from "./pages/ReaderPage";
import { FavoritesPage } from "./pages/FavoritesPage";

export default function App() {
  return (
    <div className="app">
      <header className="site-head">
        <div className="brand">
          <span className="brand-mark">R</span>
          <span className="brand-text">
            英语泛读
            <small>中英双语 · 安静阅读</small>
          </span>
        </div>
        <nav className="site-nav">
          <NavLink to="/" end>
            文章
          </NavLink>
          <NavLink to="/favorites">收藏</NavLink>
        </nav>
      </header>

      <main className="site-main">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/read/:id" element={<ReaderPage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
          <Route path="*" element={<HomePage />} />
        </Routes>
      </main>

      <footer className="site-foot">
        只读站点 · 数据来自 Supabase articles 表 · 收藏保存在本地浏览器
      </footer>
    </div>
  );
}
