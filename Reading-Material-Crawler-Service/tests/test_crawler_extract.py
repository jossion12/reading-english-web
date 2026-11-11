"""内置网页清洗提取器的单元测试（不触网）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.crawler import builtin_extract

NESTED_HTML = """
<html>
<head><title>标题</title><script>var x = 1;</script><style>.a{color:red}</style></head>
<body>
  <nav>导航 首页 关于 登录</nav>
  <div class="content_desc">
    <p>第一段正文内容，这里是新闻的主要部分，文本需要足够长才能通过两百字的下限检查。</p>
    <div class="inner">
      <p>第二段正文内容，同样属于文章主体部分，继续补充文字让正文长度达到要求，
         这样提取器才能正确识别正文区域而不会在第一个结束标签处就截断。</p>
    </div>
    <p>第三段正文内容，补充更多文字确保正文长度充足，测试嵌套结构的提取是否正确。</p>
  </div>
  <aside>侧边栏 推荐阅读 广告</aside>
  <footer>版权所有 京ICP备</footer>
</body>
</html>
"""

FLAT_HTML = """
<html><body>
  <div class="article">
    <h1>新闻标题</h1>
    <p>正文第一段，讲的是某个社区的志愿者连续三年为独居老人送饭的故事，内容朴素而具体。</p>
    <p>正文第二段，补充了更多细节，包括他们如何结对、如何排班，以及老人对这件事的真实反馈。</p>
  </div>
  <div class="related">相关阅读 其他新闻</div>
</body></html>
"""


def test_extract_nested_body_not_truncated() -> None:
    out = builtin_extract(NESTED_HTML, "http://example.test/a")
    assert "第二段正文内容" in out, "嵌套 div 内的正文被截断了"
    assert "第三段正文内容" in out
    assert len(out) >= 120


def test_extract_drops_navigation_and_footer() -> None:
    out = builtin_extract(NESTED_HTML, "http://example.test/a")
    assert "导航 首页" not in out
    assert "版权所有" not in out
    assert "侧边栏" not in out
    assert "var x = 1" not in out


def test_extract_prefers_content_container() -> None:
    out = builtin_extract(FLAT_HTML, "http://example.test/b")
    assert "正文第一段" in out
    assert "正文第二段" in out
    assert "相关阅读" not in out


def test_extract_handles_empty_input() -> None:
    assert builtin_extract("", "http://example.test/c") == ""
