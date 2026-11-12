/**
 * 图标集：全部手写 SVG，1.7px 描边、圆角端点。
 *
 * 不用 emoji —— 各平台 emoji 字体差异大，混排时字号基线和颜色都对不齐，
 * 而这个站点要在一台设备上长时间阅读，图标必须稳定。
 */

interface IconProps {
  className?: string;
}

const BASE = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

/** 书本：品牌标识 */
export function BookIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="M4 5.6A2.6 2.6 0 0 1 6.6 3H11v16.5H6.6A2.6 2.6 0 0 0 4 22.1z" />
      <path d="M20 5.6A2.6 2.6 0 0 0 17.4 3H13v16.5h4.4A2.6 2.6 0 0 1 20 22.1z" />
    </svg>
  );
}

/** 星标：收藏。未收藏时描边，收藏后由 CSS 填充 */
export function StarIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="M12 3.6 14.5 8.7 20 9.5l-4 3.9.95 5.5L12 16.2 7.05 18.9 8 13.4l-4-3.9 5.5-.8z" />
    </svg>
  );
}

/** 文档：文章列表 */
export function DocIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="M6 3.6h7.6L18 8v11.4A1.6 1.6 0 0 1 16.4 21H7.6A1.6 1.6 0 0 1 6 19.4z" />
      <path d="M13.4 3.7V8H18" />
      <path d="M9 12.5h6M9 16h4" />
    </svg>
  );
}

/** 书签：收藏页 */
export function BookmarkIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="M6.6 3.6h10.8a1 1 0 0 1 1 1v16l-6.4-4.2-6.4 4.2v-16a1 1 0 0 1 1-1z" />
    </svg>
  );
}

/** 滑块：筛选 */
export function SlidersIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="M3.5 7h9M17 7h3.5M3.5 12h3M11 12h9.5M3.5 17h9M17 17h3.5" />
      <circle cx="14.8" cy="7" r="2.3" />
      <circle cx="8.8" cy="12" r="2.3" />
      <circle cx="14.8" cy="17" r="2.3" />
    </svg>
  );
}

/** 日历 */
export function CalendarIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <rect x="3.4" y="5" width="17.2" height="15.6" rx="3" />
      <path d="M3.4 10h17.2M8 3.2v3.6M16 3.2v3.6" />
    </svg>
  );
}

/** Aa：字体 */
export function TypeIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <text
        x="12"
        y="17.5"
        textAnchor="middle"
        fontFamily="Georgia, 'Times New Roman', serif"
        fontSize="15.5"
        fill="currentColor"
        stroke="none"
      >
        Aa
      </text>
    </svg>
  );
}

/** 左箭头 */
export function ArrowLeftIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="M14.5 5.5 8 12l6.5 6.5" />
    </svg>
  );
}

/** 右箭头 */
export function ArrowRightIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="M9.5 5.5 16 12l-6.5 6.5" />
    </svg>
  );
}

/** 下箭头 */
export function ChevronDownIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="m6.5 9.5 5.5 5.5 5.5-5.5" />
    </svg>
  );
}

/** 关闭 */
export function CloseIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="m6.5 6.5 11 11M17.5 6.5l-11 11" />
    </svg>
  );
}

/** 段落对齐：用于「N 段」 */
export function ParagraphIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className}>
      <path d="M4 6h16M4 10.5h16M4 15h11M4 19.5h8" />
    </svg>
  );
}
