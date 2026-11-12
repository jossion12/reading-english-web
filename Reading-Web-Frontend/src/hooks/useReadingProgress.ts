import { useEffect, useState } from "react";

/**
 * 阅读进度（0 ~ 1）：按整页滚动位置算。
 *
 * deps 用来在正文异步加载完成后重算一次高度。
 */
export function useReadingProgress(deps: unknown[] = []): number {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const update = () => {
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      if (scrollable <= 8) {
        setProgress(0);
        return;
      }
      const value = window.scrollY / scrollable;
      setProgress(Math.min(1, Math.max(0, value)));
    };

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return progress;
}
