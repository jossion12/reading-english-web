/**
 * 字体设置：中英文各自可选，存浏览器 localStorage（与收藏同思路，不上传云端）。
 *
 * 只用系统自带字体，不加载任何字体文件：离线可用、包体不变、切换零延迟。
 * 代价是不同系统上同名字体的形态略有差异（Windows / macOS / iOS / Android）。
 */

/** 一款字体的展示信息。 */
export interface FontOption {
  id: string;
  /** 按钮上显示的名字 */
  label: string;
  /** 按钮上的预览文字：用中文名渲染汉字，用英文名渲染西文 */
  sample: string;
  /**
   * font-family 栈，**不带 serif / sans-serif 等通用族**。
   * 因为通用族一旦命中就会截断后面的回退链，汉字就再也用不上中文字体了。
   * 通用族统一写在 CSS 规则末尾（见 index.css）。
   */
  stack: string;
}

/** 英文字体：作用于西文字母与数字。 */
export const EN_FONTS: FontOption[] = [
  {
    id: "georgia",
    label: "Georgia",
    sample: "Georgia",
    stack: 'Georgia, "Iowan Old Style", "Times New Roman"',
  },
  {
    id: "times",
    label: "Times",
    sample: "Times New Roman",
    stack: '"Times New Roman", Times, "Liberation Serif"',
  },
  {
    id: "palatino",
    label: "Palatino",
    sample: "Palatino",
    stack: '"Palatino Linotype", "Book Antiqua", Palatino, Georgia',
  },
  {
    id: "segoe",
    label: "Segoe UI",
    sample: "Segoe UI",
    stack: '"Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial',
  },
  {
    id: "verdana",
    label: "Verdana",
    sample: "Verdana",
    stack: 'Verdana, Geneva, "DejaVu Sans"',
  },
  {
    id: "courier",
    label: "Courier",
    sample: "Courier New",
    stack: '"Courier New", Courier, "Nimbus Mono PS"',
  },
];

/** 中文字体：作用于汉字。 */
export const CN_FONTS: FontOption[] = [
  {
    id: "yahei",
    label: "微软雅黑",
    sample: "微软雅黑",
    stack: '"Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC"',
  },
  {
    id: "songti",
    label: "宋体",
    sample: "宋体",
    stack: 'SimSun, "Songti SC", STSong, "Noto Serif CJK SC"',
  },
  {
    id: "kaiti",
    label: "楷体",
    sample: "楷体",
    stack: 'KaiTi, "Kaiti SC", STKaiti, "Baoli SC"',
  },
  {
    id: "fangsong",
    label: "仿宋",
    sample: "仿宋",
    stack: 'FangSong, STFangsong, "FangSong_GB2312"',
  },
  {
    id: "heiti",
    label: "黑体",
    sample: "黑体",
    stack: 'SimHei, "Heiti SC", "Noto Sans CJK SC"',
  },
  {
    id: "dengxian",
    label: "等线",
    sample: "等线",
    stack: '"DengXian", "DengXian Light", "Microsoft YaHei", "PingFang SC"',
  },
];

/** 当前生效的字体组合。 */
export interface FontSetting {
  /** 英文（西文）字体 id */
  en: string;
  /** 中文字体 id */
  cn: string;
}

/** 默认值与站点初始外观保持一致（英文 Georgia，中文微软雅黑）。 */
export const DEFAULT_FONT_SETTING: FontSetting = {
  en: "georgia",
  cn: "yahei",
};

const STORAGE_KEY = "reading.fonts.v1";

function findOption(options: FontOption[], id: string): FontOption {
  return options.find((f) => f.id === id) ?? options[0];
}

/** 取英文（西文）字体栈。 */
export function enStack(id: string): string {
  return findOption(EN_FONTS, id).stack;
}

/** 取中文字体栈。 */
export function cnStack(id: string): string {
  return findOption(CN_FONTS, id).stack;
}

/** 读取本机保存的字体设置；没有或损坏时返回默认值。 */
export function loadFontSetting(): FontSetting {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_FONT_SETTING;
    const parsed = JSON.parse(raw) as Partial<FontSetting>;
    const en = typeof parsed.en === "string" ? parsed.en : DEFAULT_FONT_SETTING.en;
    const cn = typeof parsed.cn === "string" ? parsed.cn : DEFAULT_FONT_SETTING.cn;
    return { en, cn };
  } catch {
    return DEFAULT_FONT_SETTING;
  }
}

/** 保存字体设置；隐私模式 / 配额满时静默忽略。 */
export function saveFontSetting(setting: FontSetting): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(setting));
  } catch {
    // 存不下就只在本次会话生效
  }
}
