"""生成主流程：素材梗概 → LLM 扩写 → 自检 → 预览 → 入库。"""

from __future__ import annotations

import time
import uuid
from datetime import date
from typing import Any

from app.clients.db import DatabaseError, SupabaseClient
from app.clients.llm import LLMError, LLMProvider, build_llm
from app.config import Settings, get_settings
from app.material import assign_facts, split_material_sections
from app.parse import ParseError, parse_article
from app.prompts import PromptError, PromptLibrary, get_prompts
from app.schemas import (
    ArticlePayload,
    CommitResponse,
    GenerateRequest,
    PreviewResponse,
)
from app.store import LogStore, get_store
from app.validate import (
    ValidationReport,
    deterministic_checks,
    merge_llm_check,
)


class GenerationError(RuntimeError):
    """生成流程失败，message 面向管理员，附带可读原因。"""

    def __init__(self, message: str, *, status_code: int = 502, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}


class ArticleGenerator:
    #: 词数/段落数/编造事实不合格时，允许模型自我重写的次数
    MAX_REWRITE = 4
    #: 二次自检（判官）调用的重试次数 —— 模型侧偶发 500 不该把整篇判死
    SELF_CHECK_RETRIES = 3

    def __init__(
        self,
        settings: Settings | None = None,
        llm: LLMProvider | None = None,
        db: SupabaseClient | None = None,
        prompts: PromptLibrary | None = None,
        store: LogStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm = llm or build_llm(self.settings)
        self.db = db or SupabaseClient(self.settings)
        self.prompts = prompts or get_prompts()
        self.store = store or get_store()

    # ------------------------------------------------------------------
    # 预览（PRD §2.5 第 1 步）
    # ------------------------------------------------------------------
    def preview(self, req: GenerateRequest) -> PreviewResponse:
        summary = (req.summary or "").strip()

        # source_id 给了但没给梗概 —— 自动从 source_log 取
        if req.source_id and not summary:
            try:
                source = self.db.get_source(req.source_id)
            except DatabaseError as exc:
                raise GenerationError(f"读取素材失败: {exc}", status_code=502) from exc
            if source is None:
                raise GenerationError(
                    f"素材不存在: {req.source_id}", status_code=404,
                    detail={"source_id": req.source_id},
                )
            summary = (source.get("source_summary") or "").strip()

        if not req.evergreen and not summary:
            raise GenerationError(
                "非常青模式必须提供 summary 或 source_id", status_code=422,
                detail={"field": "summary"},
            )

        # 素材拆成事实句 + 禁止项：模型按「事实清单」写，编造空间被压到最小
        sections, prohibitions = split_material_sections(summary)
        facts = [fact for _, sentences in sections for fact in sentences]

        try:
            system, user = self.prompts.render_expansion(
                summary=summary,
                level=req.level,
                evergreen=req.evergreen,
                theme=req.theme,
                sub_theme=req.sub_theme,
                sections=sections,
                prohibitions=prohibitions,
            )
        except PromptError as exc:
            raise GenerationError(f"Prompt 模板错误: {exc}", status_code=500) from exc

        # --- 生成 + 自检 + 重写循环（PRD §2.3） ---
        # 每一轮：生成 → 代码自检 → LLM 二次自检 → 不通过就把问题回喂让模型重写。
        # 词数、段落配对、中文纯度、编造事实、敏感内容都在这个闭环里。
        min_words, max_words = self.prompts.word_range(req.level)
        para_cfg = self.prompts.level_config(req.level).get("para_range")
        para_range = (int(para_cfg[0]), int(para_cfg[1])) if para_cfg else None

        attempts: list[tuple[str, Any, ValidationReport]] = []
        current_user = user
        raw = ""
        parsed = None
        report = ValidationReport()

        parse_error: ParseError | None = None
        parse_error_raw = ""

        for attempt in range(self.MAX_REWRITE + 1):
            try:
                raw = self.llm.chat_json(system, current_user)
            except LLMError as exc:
                if attempt == 0:
                    self._log_failure(req, summary, str(exc))
                    raise GenerationError(f"LLM 调用失败: {exc}", status_code=502) from exc
                break
            try:
                parsed = parse_article(raw)
            except ParseError as exc:
                # 模型偶尔会吐出残缺 JSON —— 这属于可重试的偶发问题，
                # 不能因为第一轮没解析出来就把整个请求判死。
                parse_error = exc
                parse_error_raw = raw
                if attempt < self.MAX_REWRITE:
                    current_user = (
                        f"{user}\n\n"
                        + "## Your previous reply could not be parsed as JSON.\n"
                        + f"The parser said: {exc}\n"
                        + "Reply with ONE complete JSON object and nothing else. It must have "
                        + "all four fields: title_en, title_cn, english_paras, chinese_paras. "
                        + "Do not add any text before or after the JSON."
                    )
                    continue
                break

            report = deterministic_checks(
                english_paras=parsed.english_paras,
                chinese_paras=parsed.chinese_paras,
                min_words=min_words,
                max_words=max_words,
                para_range=para_range,
            )
            report = self._llm_self_check(
                report,
                summary=summary,
                level=req.level,
                parsed=parsed,
                min_words=min_words,
                max_words=max_words,
                facts=facts,
            )
            attempts.append((raw, parsed, report))

            if report.passed:
                break
            if attempt < self.MAX_REWRITE:
                current_user = (
                    f"{user}\n\n"
                    + self._rewrite_feedback(
                        report,
                        min_words,
                        max_words,
                        req.level,
                        sections=sections,
                        previous_english=list(parsed.english_paras),
                    )
                )

        if not attempts:
            # 所有轮次都没能解析出结构 —— 这才是真失败
            if parse_error is not None:
                self._log_failure(req, summary, str(parse_error), llm_raw=parse_error_raw)
                raise GenerationError(
                    f"LLM 返回内容解析失败（重试 {self.MAX_REWRITE} 次仍无法解析）: {parse_error}",
                    status_code=502,
                    detail={"llm_raw_preview": parse_error_raw[:800]},
                ) from parse_error
            raise GenerationError("所有生成尝试都无法解析出文章结构", status_code=502)

        # 选「问题最少、词数最贴近区间中值」的那一版，而不是最后一版
        def _score(item: tuple[str, Any, ValidationReport]) -> tuple[int, int, int]:
            _, _, rep = item
            failed = (
                (0 if rep.word_count_ok else 1)
                + (0 if rep.para_match else 1)
                + (0 if rep.para_count_ok else 1)
                + (0 if rep.chinese_purity else 1)
                + (0 if rep.no_fabrication else 1)
                + (0 if rep.no_sensitive else 1)
            )
            distance = abs(rep.word_count - (min_words + max_words) // 2)
            return (failed, 0 if rep.para_match else 1, distance)

        raw, parsed, report = sorted(attempts, key=_score)[0]

        payload = ArticlePayload(
            title_en=req.title_en or parsed.title_en,
            title_cn=req.title_cn or parsed.title_cn,
            english_paras=parsed.english_paras,
            chinese_paras=parsed.chinese_paras,
            level=req.level,
            theme=req.theme,
            sub_theme=req.sub_theme,
            style=req.style,
            color_tag=req.color_tag,
            publish_date=req.publish_date or date.today(),
            sort=req.sort,
            is_published=req.is_published,
            source_id=req.source_id,
        )

        ready = report.passed
        record = self.store.append(
            {
                "status": "preview",
                "level": req.level,
                "style": req.style,
                "theme": req.theme,
                "sub_theme": req.sub_theme,
                "source_id": req.source_id,
                "publish_date": payload.publish_date.isoformat(),
                "summary": summary,
                "llm_raw": raw,
                "validation": report.to_dict(),
                "payload": payload.model_dump(mode="json"),
                "article_id": None,
                "error": None,
            }
        )

        return PreviewResponse(
            draft_id=record["id"],
            payload=payload,
            validation=report,
            ready_to_commit=ready,
            llm_raw=raw,
            created_at=record["created_at"],
        )

    # ------------------------------------------------------------------
    # 入库（PRD §2.5 第 2 步）
    # ------------------------------------------------------------------
    def commit(self, draft_id: str, force: bool = False) -> CommitResponse:
        record = self.store.get(draft_id)
        if record is None:
            raise GenerationError(f"草稿不存在: {draft_id}", status_code=404)

        if record.get("status") == "committed" and record.get("article_id"):
            return CommitResponse(
                ok=True,
                article_id=record["article_id"],
                message="该草稿已入库，未重复写入",
                article=record.get("article_row"),
            )

        validation = ValidationReport.from_dict(record.get("validation") or {})
        if not validation.passed and not force:
            raise GenerationError(
                "自检未通过，已阻止入库；请修正后重新预览，或使用 force=true 强制入库",
                status_code=422,
                detail={"validation": validation.to_dict()},
            )

        payload = record.get("payload") or {}
        row = {
            "publish_date": payload.get("publish_date"),
            "title_en": payload.get("title_en"),
            "title_cn": payload.get("title_cn"),
            "level": payload.get("level"),
            "theme": payload.get("theme"),
            "sub_theme": payload.get("sub_theme") or None,
            "style": payload.get("style"),
            "color_tag": payload.get("color_tag"),
            "english_paras": payload.get("english_paras"),
            "chinese_paras": payload.get("chinese_paras"),
            "sort": payload.get("sort") or 0,
            "is_published": payload.get("is_published", False),
            "source_id": payload.get("source_id") or None,
        }

        try:
            inserted = self.db.insert_article(row)
        except DatabaseError as exc:
            self.store.update(draft_id, {"status": "failed", "error": str(exc)})
            raise GenerationError(f"写入 articles 失败: {exc}", status_code=502) from exc

        article_id = inserted.get("id")
        self.store.update(
            draft_id,
            {"status": "committed", "article_id": article_id, "article_row": inserted},
        )

        return CommitResponse(
            ok=True,
            article_id=article_id,
            message="已写入 articles 表",
            article=inserted,
        )

    # ------------------------------------------------------------------
    def _llm_self_check(
        self,
        report: ValidationReport,
        *,
        summary: str,
        level: str,
        parsed: Any,
        min_words: int,
        max_words: int,
        facts: list[str] | None = None,
    ) -> ValidationReport:
        """LLM 二次校验：是否编造事实 / 是否含敏感内容 / 段落是否真的互为翻译。"""
        last_error: Exception | None = None
        # 判官调用偶发失败（模型侧 500 / 截断）是可重试的，不该把整篇判死
        for attempt in range(self.SELF_CHECK_RETRIES):
            try:
                check_system, check_user = self.prompts.render_self_check(
                    summary=summary,
                    level=level,
                    title_en=parsed.title_en,
                    title_cn=parsed.title_cn,
                    english_paras=parsed.english_paras,
                    chinese_paras=parsed.chinese_paras,
                    facts=facts,
                )
                from app.clients.llm import extract_json

                check_raw = self.llm.chat_json(check_system, check_user, temperature=0.2)
                llm_check = extract_json(check_raw)
                return merge_llm_check(
                    report, llm_check, min_words=min_words, max_words=max_words
                )
            except (LLMError, ParseError) as exc:
                last_error = exc
                if attempt < self.SELF_CHECK_RETRIES - 1:
                    time.sleep(1.5 * (attempt + 1))
        report.issues.append(
            f"LLM 二次校验调用失败（{last_error}），可人工核对后以 force=true 入库"
        )
        return report

    # ------------------------------------------------------------------
    def _rewrite_feedback(
        self,
        report: ValidationReport,
        min_words: int,
        max_words: int,
        level: str,
        sections: list[tuple[str, list[str]]] | None = None,
        previous_english: list[str] | None = None,
    ) -> str:
        """把自检不通过的原因回喂给模型，并给出具体的形状指令。"""
        para_count = self.prompts.para_count(level)
        para_target = self.prompts.para_target(level)
        para_cfg = self.prompts.level_config(level).get("para_range") or [3, 5]
        para_low, para_high = int(para_cfg[0]), int(para_cfg[1])
        lines = ["## Your previous attempt was rejected. Rewrite the whole passage from scratch.", ""]
        # 先把上一版摆出来：不看自己写了什么，模型只会重犯同样的毛病
        if previous_english:
            lines.append("## Your previous attempt (English paragraphs)")
            for idx, para in enumerate(previous_english, 1):
                lines.append(f"Paragraph {idx}: {para}")
            lines.append("")
        lines.append(
            f"Write exactly {para_count} paragraphs in the English array and exactly "
            f"{para_count} in the Chinese array."
        )
        # 事实清单 + 逐段派活：重写时也必须按这个分工来
        if sections:
            assignment = assign_facts(sections, para_count)
            flat = [fact for _, sentences in sections for fact in sentences]
            index_of = {fact: i + 1 for i, fact in enumerate(flat)}
            lines.append("")
            lines.append("Write each paragraph from its own facts only:")
            for idx, group in enumerate(assignment, 1):
                if group:
                    refs = ", ".join(f"F{index_of[fact]}" for fact in group)
                else:
                    refs = "restate the assigned facts from another angle"
                lines.append(f"  - Paragraph {idx}: {refs}")
            lines.append(
                "The F-list in the task above is the complete set of facts you may use. "
                "Do not write about anything that is not on it."
            )
        lines.append(
            f"Each English paragraph must be at least {self.prompts.para_min(level)} words long "
            f"(aim for about {para_target} words), so the total lands between "
            f"{min_words} and {max_words} words."
        )
        # 句数是小模型唯一能稳定执行的长度约束 —— 每次回喂都要给
        sent_lo, sent_hi = self.prompts.sentences_per_para(level)
        lines.append(
            f"Put {sent_lo} to {sent_hi} sentences in EACH English paragraph "
            f"({sent_lo * para_count} to {sent_hi * para_count} sentences in the whole passage). "
            f"Count the sentences as you write them."
        )
        if not report.word_count_ok:
            deficit = min_words - report.word_count
            lines.append(
                f"- The English text had {report.word_count} words but must have between "
                f"{min_words} and {max_words}. "
                + (f"It is {deficit} words short. " if deficit > 0 else
                   f"It is {report.word_count - max_words} words too long. ")
                + ("Add more sentences, but only by unpacking what the material already "
                   "says: split one material sentence into two, restate the same fact "
                   "from the other side, walk through the same sequence step by step, or "
                   "use the material's closing significance line. Do NOT add a new fact, "
                   "name, place, number or reason. "
                   if deficit > 0 else
                   f"Use the lower end of the sentence range ({sent_lo} sentences per paragraph) "
                   f"and delete the least important sentences, keeping the passage near "
                   f"{(min_words + max_words) // 2} words.")
            )
        if not report.para_count_ok:
            # 小模型最常犯的毛病就是少写段落，而回喂里必须点明「你写了 N 段」
            lines.append(
                f"- You wrote {report.para_count} paragraphs, but this passage needs "
                f"{para_low}-{para_high} paragraphs (aim for {para_count}). "
                f"Split your content into {para_count} paragraphs — do not merge paragraphs "
                f"and do not write fewer than {para_low}."
            )
        if not report.para_match:
            lines.append(
                "- The English and Chinese paragraph arrays had different lengths. "
                "They MUST contain exactly the same number of elements, in the same order."
            )
        if not report.chinese_purity:
            lines.append(
                "- Some Chinese paragraphs still contain untranslated English words. "
                "Write every Chinese paragraph in Chinese."
            )
        if not report.no_fabrication:
            lines.append(
                "- You added facts that are NOT in the material. Every noun, modifier, "
                "number, place and reason in the passage must already appear in the "
                "material. If the material does not say it, do not write it."
            )
            lines.append(
                "- Delete these kinds of additions completely: a reason or a cause "
                "(\"the student was sick\", \"because ...\"), a starting point the person "
                "came from (\"she left her school\"), a modifier the material does not "
                "use (\"new textbooks\", \"big hills\"), a count narrower than the "
                "material gives (material says 学生们 / students → never \"a student\"), "
                "and any motive, feeling or evaluation of the people involved."
            )
            lines.append(
                "- Keep the material's own wording: 课本 → textbooks (not \"new "
                "textbooks\"), 两个山头 → two mountain tops (not \"big hills\"), "
                "学生们 → students (not \"a student\"), 学生家 → the students' homes "
                "(not \"her school\")."
            )
            lines.append(
                "- Keep every place name, school and number exactly as the material "
                "writes it (黔东南 → QianDongNan or \"a mountainous area in the "
                "province\"). If you are unsure of a name, describe it generically — "
                "never invent one. Never write what did NOT happen (\"she did not stay "
                "home that day\", \"no one helped her\"), never add a time qualifier "
                "(\"today\", \"that day\"), never write \"news reports say\"."
            )
        if not report.no_sensitive:
            lines.append(
                "- The passage contains sensitive or negative content. "
                "Rewrite it so it stays suitable for a 12-year-old reader."
            )
        # 判官指出的具体问题必须回喂给模型 —— 只给通用规则它改不对
        generic = (
            "LLM 复核判定存在梗概以外的编造事实",
            "LLM 复核判定包含敏感或负面内容",
            "LLM 复核判定中英段落数不一致",
        )
        detailed = [
            i
            for i in report.issues
            if "词数" not in i
            and "段落数不一致" not in i
            and "中文残留英文" not in i
            and "段落数" not in i
            and i not in generic
        ]
        if detailed:
            # 判官的意见是「Remove 'xxx' — …」这种祈使句，原样回喂最有效；
            # 但仍可能又长又绕（还常自相矛盾），截断后只留结论，避免模型被噪声带偏
            notes = [i.strip()[:200] for i in detailed[:3]]
            lines.append(
                "- The checker named these exact problems. Delete the sentences they "
                "quote — delete the whole sentence if it contains one of them, do not "
                "soften, reword or explain them: "
                + " | ".join(notes)
                + ". Ignore any comment that says a detail is 'not strictly a fabrication'."
            )
            lines.append(
                "- Write the passage from scratch this time. Do not reuse a sentence "
                "from your previous attempt that contains a word the material does "
                "not contain."
            )
        lines.append("")
        lines.append("Reply with the complete corrected JSON object only.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def _log_failure(
        self,
        req: GenerateRequest,
        summary: str,
        error: str,
        llm_raw: str = "",
    ) -> None:
        try:
            self.store.append(
                {
                    "status": "failed",
                    "level": req.level,
                    "style": req.style,
                    "theme": req.theme,
                    "sub_theme": req.sub_theme,
                    "source_id": req.source_id,
                    "publish_date": (req.publish_date or date.today()).isoformat(),
                    "summary": summary,
                    "llm_raw": llm_raw,
                    "validation": ValidationReport().to_dict(),
                    "payload": None,
                    "article_id": None,
                    "error": error,
                }
            )
        except Exception:  # pragma: no cover - 日志失败不应掩盖主流程错误
            pass


_generator: ArticleGenerator | None = None


def get_generator() -> ArticleGenerator:
    global _generator
    if _generator is None:
        _generator = ArticleGenerator()
    return _generator


def new_draft_id() -> str:  # pragma: no cover - 供测试使用
    return uuid.uuid4().hex
