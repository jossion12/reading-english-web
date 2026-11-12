/**
 * 难度档位。
 *
 * L1/L2/L3 是后台给的原始值；对学生来说「较易 / 中等 / 较难」比代号更直观，
 * 所以两个都给：徽标上写 L2，旁边补「中等」。
 */
export interface LevelMeta {
  /** 代号，L1 / L2 / L3 */
  short: string;
  /** 口语化的难度说明 */
  label: string;
  /** 对应的配色 class 后缀 */
  tone: string;
}

const LEVELS: Record<string, LevelMeta> = {
  L1: { short: "L1", label: "较易", tone: "l1" },
  L2: { short: "L2", label: "中等", tone: "l2" },
  L3: { short: "L3", label: "较难", tone: "l3" },
};

export function levelMeta(level: string): LevelMeta {
  return LEVELS[level] ?? { short: level, label: "", tone: "" };
}

/** 三档难度，供首页快捷筛选用。 */
export const LEVEL_ORDER = ["L1", "L2", "L3"];
