# 私人卡片目录馆 · Personal Card Catalog

OpenBiliClaw 前端的设计系统。桌面 Web（`/web`）、移动 Web（`/m`）与插件侧边栏共用同一套 token 与组件词汇；这里不存在第二套色板。

## 世界

一间只属于你的卡片目录室：卡纸躺在工作台上，印刷细线是结构，黄铜标签属于抽屉，唯一的彩色是印章红。每条推荐是一张编目卡，「为什么推给你」是管理员批注，喜欢/不感兴趣是盖在卡角上的章，看过的卡打孔归档。文字：正文用系统无衬线，元数据与标签一律等宽字体（卡片是打出来的）。

## 文件结构

```
shared/design/
  tokens.css          调色板 / 字号 / 间距 / 几何 / 动效；含 light·dark 双主题与旧 token 桥接
  base.css            元素级印刷：标题、表单控件、表格、代码、滚动条、骨架、印章动效
  world.css           组件词汇：柜体顶栏、抽屉标签、编目卡、批注块、印章、流通单、导卡分隔、表单、抽屉/遮罩
  pages/
    desktop.css       桌面壳：粘性左柜（抽屉+流通单）+ 卡盘主列
    mobile.css        移动壳：顶栏条、Tab 索引栏、紧凑卡、精简惊喜卡
    home.css          卡盘：惊喜卡、推荐网格、平台分隔、池状态
    library.css       内容库：稍后再看 / 收藏 / 30 天历史
    profile.css       画像：记录卡、量尺、推想票、内联编辑表单
    chat.css          对话台：会话夹、信纸气泡、agent 卡片与两个抽屉
    settings.css      设置（订单式表单）：实例、路由、来源卡片、台账、主题、诊断
```

## 不变量

- 颜色/间距/字号/圆角/阴影**只能**来自 `tokens.css`；页面文件里不允许出现字面色值。
- 圆角 ≤ 2px（胶囊 999px）；立体感只用 `--lift` / `--lift-hi`，禁止发光与彩色渐变（卡纸纹理由 `repeating-linear-gradient` 打点，属于印刷网点）。
- 每个状态钩子（`is-open` / `is-active` / `aria-selected` / `hidden`…）由 JS 拥有，CSS 只读取，不改名。
- 主题：`obc.theme`（显式 light/dark，缺省跟随系统）与 `obc.themeHue`（印章色相，写入 `--hue-primary`）。
- 抽屉与遮罩的显隐契约：`.drawer` / `.overlay` 默认 `display:none`，`.is-open` 才出现。
- `tokens.css` 末尾的「旧 token 桥接」把已退役的调色板名字（`--brand` / `--text-muted` / `--surface`…）映射到新世界，供仍在写内联样式的渲染器使用；新代码一律用新名字。