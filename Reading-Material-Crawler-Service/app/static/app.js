/* Reading Material Crawler Service · 素材库管理页 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );

  const state = { config: null, candidates: [], selected: null, summary: null };

  // ------------------------------------------------------------------ toast
  let toastTimer = null;
  function toast(message, kind = "") {
    const el = $("toast");
    el.textContent = message;
    el.className = "toast " + kind;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.hidden = true), kind === "err" ? 6000 : 3000);
  }

  async function api(path, options = {}) {
    const resp = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const text = await resp.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { detail: text };
    }
    if (!resp.ok) {
      const detail =
        (data && (data.detail || data.error)) || `HTTP ${resp.status}`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  // ------------------------------------------------------------------ tabs
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
      btn.classList.add("active");
      $("view-" + btn.dataset.view).classList.add("active");
      if (btn.dataset.view === "library") loadLibrary();
      if (btn.dataset.view === "logs") loadLogs();
    });
  });

  // ---------------------------------------------------------------- config
  async function loadConfig() {
    state.config = await api("/api/v1/config");
    const theme = $("theme");
    theme.innerHTML = Object.keys(state.config.themes)
      .map((name) => `<option value="${esc(name)}">${esc(name)}</option>`)
      .join("");
    const tr = $("time-range");
    tr.innerHTML = Object.entries(state.config.time_ranges)
      .map(([k, v]) => `<option value="${esc(k)}"${k === "week" ? " selected" : ""}>${esc(v.label || k)}</option>`)
      .join("");
  }

  async function loadHealth() {
    const el = $("health");
    try {
      const h = await api("/health");
      const sx = h.searxng && h.searxng.ok;
      el.className = "status " + (sx ? "ok" : "bad");
      el.textContent = `${h.llm_model} · SearXNG ${sx ? "在线" : "离线"}`;
    } catch (e) {
      el.className = "status bad";
      el.textContent = "服务不可达";
    }
  }

  // ---------------------------------------------------------------- search
  $("btn-search").addEventListener("click", async () => {
    const btn = $("btn-search");
    btn.disabled = true;
    btn.textContent = "检索中…";
    $("search-result").innerHTML = '<div class="empty">检索中…</div>';
    try {
      const body = {
        theme: $("theme").value,
        time_range: $("time-range").value,
        keyword: $("keyword").value.trim() || null,
      };
      const data = await api("/api/v1/search", {
        method: "POST",
        body: JSON.stringify(body),
      });
      state.candidates = data.candidates;
      renderSearchResult(data);
    } catch (e) {
      $("search-result").innerHTML = `<div class="notice err">检索失败：${esc(e.message)}</div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = "检索";
    }
  });

  function renderSearchResult(data) {
    const box = $("search-result");
    const cands = data.candidates || [];
    if (!cands.length) {
      const hint = data.exhausted
        ? "本次检索没有合格素材。可切换备选主题重新检索，或让上游生成服务使用常青素材兜底（PRD §2.8）。"
        : "";
      const errs = (data.errors || []).map((e) => `<div class="notice err">${esc(e)}</div>`).join("");
      box.innerHTML = `${errs}<div class="notice warn">${esc(hint || "没有符合白名单/黑名单规则的候选。")}</div>`;
      return;
    }
    const dropped = Object.entries(data.dropped || {})
      .map(([k, v]) => `${k}=${v}`)
      .join(" · ");
    const fallback = data.fallback_used
      ? `<div class="notice warn">SearXNG 未返回可用候选，已自动改用 <strong>RSS 直采</strong>兜底通道（来源：${esc(
          (data.sources_used || []).join("、")
        )}）。</div>`
      : "";
    const unmatched = data.keyword_unmatched
      ? `<div class="notice warn">关键词没有命中任何候选，下面给出的是最新候选，换个关键词或直接点选也可以。</div>`
      : "";
    const budget = data.budget_exhausted
      ? `<div class="notice info">SearXNG 上游引擎长时间无响应，已提前切换到兜底通道以免一直等待。</div>`
      : "";
    box.innerHTML =
      `${fallback}${unmatched}${budget}` +
      `<p class="hint">命中 ${cands.length} 条候选；已过滤 ${esc(dropped)}</p>` +
      cands
        .map(
          (c, i) => `
      <div class="candidate" data-idx="${i}">
        <div class="title">${esc(c.title)}</div>
        <div class="meta">
          <span class="badge">${esc(c.domain)}</span>
          <span class="badge src">${esc(c.engine || "searxng")}</span>
          ${c.published_date ? `<span>${esc(c.published_date)}</span>` : ""}
          <span class="mono">${esc(c.url)}</span>
        </div>
        ${c.summary ? `<div class="summary">${esc(c.summary.slice(0, 180))}</div>` : ""}
      </div>`
        )
        .join("");

    box.querySelectorAll(".candidate").forEach((el) => {
      el.addEventListener("click", () => {
        box.querySelectorAll(".candidate").forEach((c) => c.classList.remove("selected"));
        el.classList.add("selected");
        state.selected = state.candidates[Number(el.dataset.idx)];
        extract(state.selected.url);
      });
    });
  }

  // -------------------------------------------------------------- extract
  async function extract(url) {
    $("card-extract").hidden = false;
    $("extract-body").innerHTML = '<div class="empty">抓取清洗 + 梗概提炼中，请稍候…</div>';
    $("card-confirm").hidden = true;
    try {
      const data = await api("/api/v1/summarize", {
        method: "POST",
        body: JSON.stringify({ url }),
      });
      state.summary = data;
      renderSummary(data);
    } catch (e) {
      $("extract-body").innerHTML = `<div class="notice err">处理失败：${esc(e.message)}</div>`;
    }
  }

  function renderSummary(data) {
    const s = data.summary;
    const dup = data.duplicated;
    $("extract-body").innerHTML = `
      <div class="row spread">
        <span class="badge">清洗引擎 ${esc(data.crawl_engine)}</span>
        <span class="badge ${dup ? "err" : "ok"}">${dup ? "素材已存在" : "查重通过"}</span>
      </div>
      ${
        dup
          ? `<div class="notice err">${
              data.duplicate_reason === "url"
                ? "该来源链接已入库"
                : "该梗概已入库"
            }（素材 id <code>${esc(data.existing?.id)}</code>），已阻断后续入库流程。请返回候选列表重选。</div>`
          : ""
      }
      <div class="summary-box mt">${esc(s.text)}</div>
      <p class="hint">指纹 ${esc(data.fingerprint)}（口径 ${esc(data.fingerprint_mode)}）</p>
      <label class="hint">备注（来源链接、说明）</label>
      <input id="remark" type="text" class="mt" style="width:100%" placeholder="来源链接或备注" value="${esc(data.url || "")}" />
      <p class="hint">来源链接会自动记入备注，并作为查重依据（同一篇报道不会被收两遍）。</p>
    `;

    $("card-confirm").hidden = false;
    $("confirm-body").innerHTML = `
      <div class="row">
        <button class="primary" id="btn-save" ${dup ? "disabled" : ""}>确认入库</button>
        <button id="btn-cancel">取消</button>
      </div>
      <p class="hint">入库后可在「素材库」页查看、编辑备注、删除，并查看已生成的阅读文章。</p>
    `;
    $("btn-save").addEventListener("click", saveSource);
    $("btn-cancel").addEventListener("click", () => {
      $("card-confirm").hidden = true;
    });
  }

  async function saveSource() {
    const btn = $("btn-save");
    btn.disabled = true;
    try {
      const text = state.summary.summary.text;
      const row = await api("/api/v1/sources", {
        method: "POST",
        body: JSON.stringify({
          summary_text: text,
          fingerprint: state.summary.fingerprint,
          remark: $("remark")?.value.trim() || null,
          source_url: state.summary.url || null,
        }),
      });
      toast("已入库，素材 id " + row.id, "ok");
      $("card-confirm").hidden = true;
    } catch (e) {
      toast("入库失败：" + e.message, "err");
    } finally {
      btn.disabled = false;
    }
  }

  // -------------------------------------------------------------- library
  async function loadLibrary() {
    const box = $("library-list");
    box.innerHTML = '<div class="empty">加载中…</div>';
    try {
      const rows = await api("/api/v1/sources?limit=200");
      if (!rows.length) {
        box.innerHTML = '<div class="empty">素材库为空，先去「采集」页抓一条。</div>';
        return;
      }
      box.innerHTML = `<table>
        <thead><tr>
          <th style="width:34%">梗概</th><th style="width:18%">备注 / 来源</th>
          <th style="width:12%">录入时间</th><th style="width:14%">关联文章</th><th></th>
        </tr></thead>
        <tbody>${rows
          .map(
            (r) => `<tr>
          <td><div style="max-height:96px;overflow:auto">${esc(r.source_summary)}</div>
              <div class="mono">${esc(r.source_fingerprint.slice(0, 16))}…</div></td>
          <td><div id="remark-${esc(r.id)}">${esc(r.remark || "—")}</div></td>
          <td class="mono">${esc((r.create_at || "").slice(0, 19).replace("T", " "))}</td>
          <td><button class="small" data-related="${esc(r.id)}">查看</button></td>
          <td class="actions">
            <button class="small" data-edit="${esc(r.id)}">改备注</button>
            <button class="small danger" data-del="${esc(r.id)}">删除</button>
          </td>
        </tr>`
          )
          .join("")}</tbody></table>`;

      box.querySelectorAll("[data-edit]").forEach((b) =>
        b.addEventListener("click", () => editRemark(b.dataset.edit))
      );
      box.querySelectorAll("[data-del]").forEach((b) =>
        b.addEventListener("click", () => removeSource(b.dataset.del))
      );
      box.querySelectorAll("[data-related]").forEach((b) =>
        b.addEventListener("click", () => showRelated(b.dataset.related))
      );
    } catch (e) {
      box.innerHTML = `<div class="notice err">加载失败：${esc(e.message)}</div>`;
    }
  }

  async function editRemark(id) {
    const row = await api("/api/v1/sources/" + id);
    const next = prompt("修改备注：", row.remark || "");
    if (next === null) return;
    try {
      await api("/api/v1/sources/" + id, {
        method: "PATCH",
        body: JSON.stringify({ remark: next }),
      });
      toast("备注已更新", "ok");
      loadLibrary();
    } catch (e) {
      toast("更新失败：" + e.message, "err");
    }
  }

  async function removeSource(id) {
    if (!confirm("确认删除该素材？已生成的文章会保留（source_id 置空）。")) return;
    try {
      await api("/api/v1/sources/" + id, { method: "DELETE" });
      toast("已删除", "ok");
      loadLibrary();
    } catch (e) {
      toast("删除失败：" + e.message, "err");
    }
  }

  async function showRelated(id) {
    try {
      const rows = await api("/api/v1/sources/" + id + "/articles");
      if (!rows.length) {
        toast("该素材尚未生成阅读文章");
        return;
      }
      const text = rows
        .map(
          (r) =>
            `- [${r.is_published ? "已发布" : "未发布"}] ${r.title_en} / ${r.title_cn} (${r.publish_date}, ${r.level})`
        )
        .join("\n");
      alert("关联阅读文章：\n\n" + text);
    } catch (e) {
      toast("查询失败：" + e.message, "err");
    }
  }

  $("btn-reload-library").addEventListener("click", loadLibrary);

  // ----------------------------------------------------------------- logs
  async function loadLogs() {
    const box = $("logs-list");
    box.innerHTML = '<div class="empty">加载中…</div>';
    try {
      const rows = await api("/api/v1/logs?limit=200");
      if (!rows.length) {
        box.innerHTML = '<div class="empty">暂无日志</div>';
        return;
      }
      box.innerHTML = rows
        .map((r) => {
          const { id, created_at, event, ...rest } = r;
          return `<div class="log-line">
            <span class="mono">${esc((created_at || "").slice(0, 19).replace("T", " "))}</span>
            <span class="event">${esc(event)}</span>
            <span class="mono">${esc(JSON.stringify(rest))}</span>
          </div>`;
        })
        .join("");
    } catch (e) {
      box.innerHTML = `<div class="notice err">加载失败：${esc(e.message)}</div>`;
    }
  }

  $("btn-reload-logs").addEventListener("click", loadLogs);

  // ------------------------------------------------------------------ init
  (async () => {
    try {
      await loadConfig();
    } catch (e) {
      toast("配置加载失败：" + e.message, "err");
    }
    loadHealth();
  })();
})();
