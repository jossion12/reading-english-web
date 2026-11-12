import { useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { BottomSheet } from "./components/BottomSheet";
import { FontPicker } from "./components/FontPicker";
import { BookIcon, BookmarkIcon, DocIcon, TypeIcon } from "./components/Icons";
import { FontProvider } from "./hooks/useFonts";
import { HomePage } from "./pages/HomePage";
import { ReaderPage } from "./pages/ReaderPage";
import { FavoritesPage } from "./pages/FavoritesPage";

/** 顶栏 = 书本的封面。手机端导航挪到底部，封面只留品牌。 */
function SiteHeader() {
  const [fontOpen, setFontOpen] = useState(false);

  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark">
          <BookIcon />
        </span>
        <span className="brand-text">
          <span className="brand-name">英语泛读</span>
          <span className="brand-sub">中英双语 · 安静阅读</span>
        </span>
      </div>

      <nav className="topnav">
        <NavLink to="/" end className={({ isActive }) => `topnav-link${isActive ? " is-active" : ""}`}>
          文章
        </NavLink>
        <NavLink to="/favorites" className={({ isActive }) => `topnav-link${isActive ? " is-active" : ""}`}>
          收藏
        </NavLink>
      </nav>

      <div className="topbar-actions">
        <button type="button" className="cover-btn" onClick={() => setFontOpen(true)}>
          <TypeIcon />
          字体
        </button>
      </div>

      <BottomSheet open={fontOpen} title="字体" onClose={() => setFontOpen(false)}>
        <FontPicker />
      </BottomSheet>
    </header>
  );
}

/** 底部导航：手机上拇指够得到的位置。 */
function TabBar() {
  const [fontOpen, setFontOpen] = useState(false);

  return (
    <>
      <nav className="tabbar" aria-label="主导航">
        <NavLink to="/" end className={({ isActive }) => `tab${isActive ? " is-active" : ""}`}>
          <DocIcon />
          <span className="tab-label">文章</span>
        </NavLink>
        <NavLink to="/favorites" className={({ isActive }) => `tab${isActive ? " is-active" : ""}`}>
          <BookmarkIcon />
          <span className="tab-label">收藏</span>
        </NavLink>
        <button type="button" className="tab" onClick={() => setFontOpen(true)}>
          <TypeIcon />
          <span className="tab-label">字体</span>
        </button>
      </nav>

      <BottomSheet open={fontOpen} title="字体" onClose={() => setFontOpen(false)}>
        <FontPicker />
      </BottomSheet>
    </>
  );
}

function SiteShell() {
  return (
    <div className="shell">
      <SiteHeader />

      <main className="site-main">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
          <Route path="*" element={<HomePage />} />
        </Routes>
      </main>

      <footer className="app-foot">
        文章来自 Supabase · 收藏与字体设置只存在这台设备上
      </footer>

      <TabBar />
    </div>
  );
}

export default function App() {
  const location = useLocation();
  // 阅读页自带一套顶栏，导航栏不出现，读的时候少一点干扰
  const isReader = location.pathname.startsWith("/read");

  return (
    <FontProvider>
      {isReader ? (
        <Routes>
          <Route path="/read/:id" element={<ReaderPage />} />
          <Route path="*" element={<SiteShell />} />
        </Routes>
      ) : (
        <SiteShell />
      )}
    </FontProvider>
  );
}
