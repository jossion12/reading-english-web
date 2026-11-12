/**
 * 字体状态：localStorage 持久化，并把选择写进 CSS 变量，全站按字符分别取字体。
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  CN_FONTS,
  DEFAULT_FONT_SETTING,
  EN_FONTS,
  cnStack,
  enStack,
  loadFontSetting,
  saveFontSetting,
  type FontOption,
  type FontSetting,
} from "../lib/fonts";

export interface FontContextValue {
  /** 当前生效的字体组合 */
  setting: FontSetting;
  /** 英文（西文）字体列表 */
  enFonts: FontOption[];
  /** 中文字体列表 */
  cnFonts: FontOption[];
  setEnFont: (id: string) => void;
  setCnFont: (id: string) => void;
  /** 恢复默认 */
  reset: () => void;
}

const FontContext = createContext<FontContextValue | null>(null);

export function FontProvider({ children }: { children: ReactNode }) {
  // 首次渲染就读本机设置，避免先闪一下默认字体
  const [setting, setSetting] = useState<FontSetting>(() => loadFontSetting());

  useEffect(() => {
    saveFontSetting(setting);
  }, [setting]);

  // 写进 CSS 变量：--font-en 管西文与数字，--font-cn 管汉字，
  // 规则里两者并排，靠浏览器按字符逐个回退。
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--font-en", enStack(setting.en));
    root.style.setProperty("--font-cn", cnStack(setting.cn));
  }, [setting]);

  const setEnFont = useCallback((id: string) => {
    setSetting((prev) => ({ ...prev, en: id }));
  }, []);

  const setCnFont = useCallback((id: string) => {
    setSetting((prev) => ({ ...prev, cn: id }));
  }, []);

  const reset = useCallback(() => {
    setSetting(DEFAULT_FONT_SETTING);
  }, []);

  const value = useMemo<FontContextValue>(
    () => ({
      setting,
      enFonts: EN_FONTS,
      cnFonts: CN_FONTS,
      setEnFont,
      setCnFont,
      reset,
    }),
    [setting, setEnFont, setCnFont, reset],
  );

  return <FontContext.Provider value={value}>{children}</FontContext.Provider>;
}

export function useFonts(): FontContextValue {
  const ctx = useContext(FontContext);
  if (!ctx) throw new Error("useFonts 必须在 FontProvider 内使用");
  return ctx;
}
