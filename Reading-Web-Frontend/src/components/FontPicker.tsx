import { useFonts } from "../hooks/useFonts";

/**
 * 字体选择器：中英文各一组，点一下立即生效。
 *
 * 每个按钮用该字体本身渲染自己的名字，所见即所得。
 * 通用族（serif / sans-serif）只允许出现在栈的最后一位 —— 一旦它先命中，
 * 后面排着的字体就再也用不上了。
 */
export function FontPicker() {
  const { setting, enFonts, cnFonts, setEnFont, setCnFont, reset } = useFonts();

  return (
    <div className="font-picker">
      <div className="font-group">
        <div className="font-group-head">
          <h4>英文字体</h4>
          <span className="hint">正文与标题的西文</span>
        </div>
        <div className="font-options">
          {enFonts.map((font) => (
            <button
              type="button"
              key={font.id}
              className={`font-chip${setting.en === font.id ? " is-active" : ""}`}
              style={{ fontFamily: `${font.stack}, serif` }}
              onClick={() => setEnFont(font.id)}
              aria-pressed={setting.en === font.id}
              title={font.label}
            >
              {font.sample}
            </button>
          ))}
        </div>
      </div>

      <div className="font-group">
        <div className="font-group-head">
          <h4>中文字体</h4>
          <span className="hint">译文与标题的汉字</span>
        </div>
        <div className="font-options">
          {cnFonts.map((font) => (
            <button
              type="button"
              key={font.id}
              className={`font-chip${setting.cn === font.id ? " is-active" : ""}`}
              style={{ fontFamily: `${font.stack}, serif` }}
              onClick={() => setCnFont(font.id)}
              aria-pressed={setting.cn === font.id}
              title={font.label}
            >
              {font.sample}
            </button>
          ))}
        </div>
      </div>

      <div className="font-foot">
        <span className="hint">只保存在这台设备上</span>
        <button type="button" className="link-btn" onClick={reset}>
          恢复默认
        </button>
      </div>
    </div>
  );
}
