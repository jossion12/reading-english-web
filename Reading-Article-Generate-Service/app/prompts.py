"""Prompt 模板加载与渲染（PRD §4.2：Prompt 模板可配置）。

模板放在 config/prompts.yaml，改完重启服务即可生效。
渲染采用 str.replace('{{KEY}}', value)，避免与 prompt 里的 JSON 花括号打架。
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import Settings, get_settings
from app.material import assign_facts, split_material, split_material_sections


class PromptError(RuntimeError):
    """模板缺失或配置错误。"""


def _render(template: str, values: dict[str, Any]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out


class PromptLibrary:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.prompts: dict[str, Any] = self._load_yaml(self.settings.prompts_path)
        self.taxonomy: dict[str, Any] = self._load_yaml(self.settings.taxonomy_path)

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise PromptError(f"配置文件不存在: {path}")
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise PromptError(f"配置文件格式错误（应为映射）: {path}")
        return data

    # --- 基础配置 ----------------------------------------------------------
    def level_config(self, level: str) -> dict[str, Any]:
        levels = self.prompts.get("expansion", {}).get("levels", {})
        if level not in levels:
            raise PromptError(f"未配置难度档位: {level}（可选: {', '.join(levels)}）")
        return levels[level]

    def word_range(self, level: str) -> tuple[int, int]:
        rng = self.level_config(level).get("word_range") or [80, 180]
        return int(rng[0]), int(rng[1])

    def default_color_tag(self, style: str) -> str:
        styles = self.taxonomy.get("styles", {})
        entry = styles.get(style) or {}
        return str(entry.get("default_color_tag") or "#E8F1FF").upper()

    def para_target(self, level: str) -> int:
        """每段目标词数 = 区间中值 ÷ 建议段落数中值。"""
        min_words, max_words = self.word_range(level)
        para_range = self.level_config(level).get("para_range") or [3, 5]
        mid_para = (int(para_range[0]) + int(para_range[1])) / 2
        return max(10, round((min_words + max_words) / 2 / mid_para))

    def para_min(self, level: str) -> int:
        """每段词数下限：区间下限 × 1.1 余量 ÷ 段落数。

        小模型对「总数 120-180」不敏感，但对「每段至少 N 词」敏感；给下限并留
        10% 余量，才不会三次都写到下限以下。
        """
        min_words, _ = self.word_range(level)
        para_count = self.para_count(level)
        return max(10, math.ceil(min_words * 1.1 / para_count))

    def para_max(self, level: str) -> int:
        """每段词数上限：段落目标词数 × 1.1。

        配合 para_min 用，构成「每段 N~M 词」的窄带。段落数固定时，
        每段 × 段落数的乘积落在难度区间内部，整篇总词数就不会再越界 ——
        这比只给一个总词数区间管用（模型写长的倾向是系统性的）。
        """
        return max(10, round(self.para_target(level) * 1.1))

    def sentences_per_para(self, level: str) -> tuple[int, int]:
        """每段句数区间。

        实测（qwen3.5:9b）：同一条「每段 N 词」的写法合格率只有 1/3，改成
        「每段 N 个句子」后合格率 3/3 —— 小模型数句子比数字数准得多，
        所以长度控制以句数为主、词数为辅。
        """
        cfg = self.level_config(level).get("sentences_per_para")
        if not cfg:
            return 4, 5
        return int(cfg[0]), int(cfg[1])

    def sent_label(self, level: str) -> str:
        """句数要求的自然语言写法。

        区间上下界相同时写成「exactly N」，否则写成「N to M」。
        模型总往区间上界写，钉死成单值比给区间更稳。
        """
        lo, hi = self.sentences_per_para(level)
        return f"exactly {lo}" if lo == hi else f"{lo} to {hi}"

    def sentences_feedback(self, level: str) -> str:
        """回喂给模型的句数指令。"""
        lo, hi = self.sentences_per_para(level)
        para_count = self.para_count(level)
        if lo == hi:
            return (
                f"Put exactly {lo} sentences in EACH English paragraph "
                f"({lo * para_count} sentences in the whole passage)."
            )
        return (
            f"Put {lo} to {hi} sentences in EACH English paragraph "
            f"({lo * para_count} to {hi * para_count} sentences in the whole passage)."
        )

    def para_count(self, level: str) -> int:
        """建议段落数：取区间中值。"""
        para_range = self.level_config(level).get("para_range") or [3, 5]
        return max(1, round((int(para_range[0]) + int(para_range[1])) / 2))

    def taxonomy_meta(self) -> dict[str, Any]:
        return {
            "levels": self.taxonomy.get("levels", {}),
            "styles": self.taxonomy.get("styles", {}),
            "themes": self.taxonomy.get("themes", {}),
        }

    # --- 素材拆解 ----------------------------------------------------------
    def material_facts(self, summary: str) -> tuple[list[str], list[str]]:
        """把梗概拆成 (事实句, 禁止项)。"""
        return split_material(summary or "")

    def material_sections(self, summary: str) -> list[tuple[str, list[str]]]:
        """把梗概按段拆开（标签 + 该段的事实句）。"""
        grouped, _ = split_material_sections(summary or "")
        return grouped

    @staticmethod
    def _fact_list(facts: list[str]) -> str:
        if not facts:
            return (
                "（素材没有标注分段，整段文字都是事实；请逐句使用素材里的每一句，"
                "不要补充素材之外的任何信息。）"
            )
        return "\n    ".join(f"F{i}. {fact}" for i, fact in enumerate(facts, 1))

    @staticmethod
    def _para_assignment(assignment: list[list[str]], facts: list[str]) -> str:
        index_of = {fact: i + 1 for i, fact in enumerate(facts)}
        lines: list[str] = []
        for idx, group in enumerate(assignment, 1):
            if group:
                refs = ", ".join(f"F{index_of[fact]}" for fact in group)
            else:
                refs = "no fact of its own — restate the assigned facts from another angle"
            lines.append(f"- Paragraph {idx} (English + Chinese): {refs}")
        return "\n    ".join(lines)

    @staticmethod
    def _prohibition_list(prohibitions: list[str]) -> str:
        if not prohibitions:
            return "（素材没有额外的禁止项。）"
        return "\n    ".join(f"- {p}" for p in prohibitions)

    # --- 模板渲染 ----------------------------------------------------------
    def render_expansion(
        self,
        *,
        summary: str,
        level: str,
        evergreen: bool = False,
        theme: str = "",
        sub_theme: str = "",
        sections: list[tuple[str, list[str]]] | None = None,
        prohibitions: list[str] | None = None,
    ) -> tuple[str, str]:
        """返回 (system_prompt, user_prompt)。"""
        cfg = self.level_config(level)
        min_words, max_words = self.word_range(level)
        level_instruction = str(cfg.get("instruction", "")).strip()
        if sections is None:
            sections, auto_prohibitions = split_material_sections(summary or "")
            if prohibitions is None:
                prohibitions = auto_prohibitions
        if prohibitions is None:
            prohibitions = []
        facts: list[str] = [fact for _, sentences in sections for fact in sentences]
        assignment = assign_facts(sections, self.para_count(level))
        values = {
            "summary": summary or "",
            "level": level,
            "min_words": min_words,
            "max_words": max_words,
            "level_instruction": level_instruction,
            "theme": theme or "",
            "sub_theme": sub_theme or "",
            "para_target": self.para_target(level),
            "para_count": self.para_count(level),
            "para_min": self.para_min(level),
            "para_max": self.para_max(level),
            "sent_lo": self.sentences_per_para(level)[0],
            "sent_hi": self.sentences_per_para(level)[1],
            "sent_label": self.sent_label(level),
            "fact_list": self._fact_list(facts),
            "para_assignment": self._para_assignment(assignment, facts),
            "prohibition_list": self._prohibition_list(prohibitions),
        }

        if evergreen:
            block = self.prompts.get("evergreen", {})
        else:
            block = self.prompts.get("expansion", {})

        system = str(block.get("system", "")).strip()
        user = _render(str(block.get("common", "")), values).strip()
        if not user:
            raise PromptError("Prompt 模板为空：expansion.common / evergreen.common")
        return system, user

    def render_self_check(
        self,
        *,
        summary: str,
        level: str,
        title_en: str,
        title_cn: str,
        english_paras: list[str],
        chinese_paras: list[str],
        facts: list[str] | None = None,
    ) -> tuple[str, str]:
        min_words, max_words = self.word_range(level)
        if facts is None:
            facts, _ = split_material(summary or "")
        evergreen_note = (
            "（常青素材：没有原始梗概。只有当内容明显不是稳定通识、"
            "或者编造了精确的数字/专名/年份时才算编造；"
            "不要因为某个普通词没出现在素材里就判成编造。）"
        )
        values = {
            "summary": summary or evergreen_note,
            "fact_list": self._fact_list(facts) if facts else evergreen_note,
            "level": level,
            "min_words": min_words,
            "max_words": max_words,
            "title_en": title_en,
            "title_cn": title_cn,
            "english_paras": "\n".join(english_paras),
            "chinese_paras": "\n".join(chinese_paras),
            "en_count": len(english_paras),
            "cn_count": len(chinese_paras),
        }
        block = self.prompts.get("self_check", {})
        system = str(block.get("system", "")).strip()
        user = _render(str(block.get("template", "")), values).strip()
        if not user:
            raise PromptError("Prompt 模板为空：self_check.template")
        return system, user


@lru_cache(maxsize=1)
def get_prompts() -> PromptLibrary:
    return PromptLibrary()
