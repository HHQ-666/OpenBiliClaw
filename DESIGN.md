# Design

<!-- impeccable:design-system -->

私人卡片目录馆 / Personal Card Catalog — OpenBiliClaw 的视觉世界。三端（桌面 `/web`、移动 `/m`、插件弹窗）共用同一套 token 与组件词汇；本文件记录**已建成**的系统，实现以 `src/openbiliclaw/web/shared/design/` 为准。

## 世界与主张

一间只属于你的卡片目录室。每条内容是一张编目卡：来源与作者是目录行，「为什么推给你」是管理员盖在卡上的批注，喜欢/不感兴趣是一枚印章，看过的卡打孔归档，后台在干活时把流通单塞进左侧抽屉。

拒绝的品类默认：奶油底＋高对比衬线＋赤陶按钮的「AI 界面」，以及「近黑＋霓虹发光」的深色套路（对应方向轮的落选说明）。粉色不再是品牌约束，唯一的彩色是印章红。

## 色彩

策略：Restrained（中性为主＋单一强调）；纸张与墨色承担全部结构，色彩只在「盖章」时出现。

| 角色 | 亮房（light） | 夜读室（dark） |
|---|---|---|
| 台面 `--desk` | `#d9d4c8` | `#15191d` |
| 卡纸 `--card` / `--card-hi` / `--card-sunk` | `#f7f5ef` / `#fdfcf9` / `#efebe1` | `#1d2329` / `#232a31` / `#191f24` |
| 墨色 `--ink` / `--ink-2` / `--ink-3` | `#1f262e` / `#58606a` / `#8b9199` | `#e8e4d8` / `#a7aeb6` / `#767d85` |
| 印刷细线 `--rule` / `--rule-soft` / `--rule-strong` | `#c6bfb0` / `#dcd7ca` / `#a49c8c` | `#363d45` / `#2a3037` / `#4d5560` |
| 印章红 `--stamp`（唯一强调） | `hsl(hue 56% 41%)`，默认 hue 8 | `hsl(hue 52% 52%)` |
| 黄铜 `--brass`（硬件：抽屉标签、agent 线） | `#8f7339` | `#a98f56` |
| 状态 `--ok` / `--warn` | `#2f6f55` / `#8a6a17` | `#5da184` / `#c1a157` |

`--hue-primary`（用户可控，来自 `obc.themeHue`）只旋转印章红与 `--stamp-soft`；卡纸、墨色、黄铜不受影响——这是「印章色相」设置的语义。对比度：两种外观下 `--ink` on `--card` 均 ≥ 7:1（契约测试锁定）。

## 字体

- 正文：系统无衬线（`-apple-system` / `PingFang SC` / `Noto Sans SC`）。
- 元数据、标签、按钮：等宽（`ui-monospace` / SF Mono / Menlo）。目录卡是打出来的——来源、日期、编号、计数、状态一律等宽，含 `font-variant-numeric: tabular-nums`。
- 标题：系统无衬线 700，`letter-spacing: -0.005em`；「label/eyebrow」用等宽小号＋0.14em 字距。
- 尺寸：display 25 / h2 21 / h3 16.5 / 标题 15.5 / 正文 14 / 注 13 / 元 11.5 / 标签 10.5。

## 几何与材料

- 圆角 ≤ 2px（索引胶囊 999px）；影印品是方的。
- 立体感只用 `--lift` / `--lift-hi`（纸抬起），禁止发光；描边（细线）是结构，不是装饰。
- 纸纹＝`repeating-linear-gradient` 网点（等宽 9–12px），只用于「无图占位/长文剪报」，不是渐变装饰。
- 斜体、彩色渐变、玻璃拟态：不用。

## 组件词汇

- **柜体顶栏**（`.topbar`）：卡纸底＋下细线；品牌牌位；检索框（等宽输入＋印刷按钮）；状态签（黄铜点/印章点）；`京 44px` 触控。
- **抽屉标签导航**（`.nav-action`）：行式标签；active＝拉出的抽屉（卡纸抬起＋左侧 3px 印章条＋右移 2px）。黄铜用于 hover/图标。
- **编目卡**（`.video-card` / `.saved-card` / `.card`）：卡纸＋细线＋纸抬起；封面 16:9、来源章在封面左下；标题 2 行截断；元数据等宽；`hover` 上浮 2px。
- **批注块**（`.reason` / `#delightReason` / `.card-expression`）：凹陷卡纸＋左侧 2px 印章条——「为什么推给你」的固定形制，桌面与手机同一语言。
- **印章**（`.feedback-icon-btn`）：30px 方章；按下（`aria-pressed`）＝印章落下（旋转 -4°＋`stamp-press` 260ms 回弹＋印章色底）；`is-neutral` 虚线空章。
- **流通单**（`.side-section`）：左侧抽屉里的运行时/动态条；点线引导行（`label … value`）、三格度量、动态项带印章点。
- **导卡分隔**（`.filter-row .chip` / `.content-library-tab` / `.settings-tab`）：平台与视图切换＝目录导卡；等宽标签＋计数列（tabular-nums）；选中＝底部 2px 印章条＋字重 600（不只靠颜色）。
- **表单**（`.settings-field` / `.edit-field`）：印刷订单：等宽标签在上、控件在下、点线分栏；开关＝印刷槽＋滑动墨块；色相＝墨垫阵列。
- **抽屉与遮罩**：`.drawer` / `.overlay` 默认 `display:none`，`.is-open` 出现，`.is-closing` 播放退出（面板右移 16px 淡出）；`prefers-reduced-motion` 全程兜底。

## 动效语法（impressions, not transitions）

- 默认 `--imp: 170ms cubic-bezier(.2,.85,.3,1)`；进场 `card-enter` 6px 升起淡入；页面进场 `page-enter` 仅透明度（不移动几何，避免指针错位）。
- 签名动作：印章按压 `stamp-press`（260ms 带 1.4 回弹，唯一允许的过冲）+ 按下态微旋 -4°。
- 骨架屏＝干胶呼吸（透明度/位移），不是流光。

## 三端映射

| | 桌面 `/web` | 移动 `/m` | 插件弹窗 |
|---|---|---|---|
| 外壳 | 粘性左柜（抽屉标签＋流通单）＋卡盘主列；`@container desktop-main` 让惊喜卡按自身宽度折列 | 顶栏条＋底部索引 Tab（active＝印章条）＋单列卡盘 | 卡纸头部＋四标签行＋单列卡盘 |
| 样式来源 | `shared/design/*`（9 个文件） | 同一套（+`pages/mobile.css`） | `popup.html` 内联镜像层（token 值与 tokens.css 对齐） |

## 不变量

1. 颜色/间距/字号/圆角/阴影只来自 `tokens.css`；页族文件零字面色值（契约测试锁定）。
2. 侧边色条必须承载语义：印章红＝批注/你的反馈，黄铜＝机器与工具，警告黄＝需要注意；不做装饰性色条。
3. 状态钩子（`is-open` / `is-active` / `aria-selected` / `aria-pressed` / `hidden`）由 JS 拥有，CSS 只消费。
4. 触控目标 ≥ 44px（`pointer: coarse` 或 ≤820px）。
5. `tokens.css` 末尾的旧 token 桥接把退役调色板名映射到新世界，供仍写内联样式的渲染器使用；新代码用新名字。