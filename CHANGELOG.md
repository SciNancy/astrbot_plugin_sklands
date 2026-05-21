# Changelog

## 2026-05-21

### 更新 11：优化 sign / mr 输出格式，减少空行

- **`/sk sign`**：
  - 将拼接符从 `\n\n`（双换行）改为 `\n`（单换行）
  - 消除角色之间的多余空行，奖励列表内部换行保持不变
- **`/sk mr`**：
  - 去掉标题后的固定空行
  - 去掉每个游戏区块末尾的固定空行
  - 仅当两个游戏都有数据时，在区块之间插入一个空行作为分隔
  - 整体从原来的每个区块后都带空行，改为仅在必要时分隔

**修改文件**：`main.py`

## 2026-05-21

### 更新 10：新增体力预警定时功能

- **功能说明**：每隔 1 小时自动检测所有绑定角色的体力（理智），当体力超过 90% 时推送预警消息
- **预警逻辑**：
  - 体力 >= 90% 且未预警过 → 发送一次消息，标记已预警
  - 体力 < 90% 且已预警过 → 重置预警状态，下次满体时再次提醒
  - 未超过 90% → 不发送任何消息
- **自动刷新 cred**：每次检测都会调用 API，借助 `call_api_with_refresh` 自动处理 Token 失效并刷新
- **UMO 记录**：
  - 新增 `SkUser.umo` 字段保存用户消息来源
  - 在 `/sk login`、`/sk bind` 时自动记录
  - 在 `/sk mr`、`/sk arkmr`、`/sk efmr` 等命令使用时自动更新
- **新增数据库表 `skland_stamina_alert`**：
  - `user_id` + `char_uid` + `game` 唯一标识一个角色的预警状态
  - `alerted` 布尔值标记是否已发送当前周期预警
  - `last_check_time` 记录最后检查时间戳
- **数据库迁移**：启动时自动检测并为旧表添加 `umo` 列，自动创建 `stamina_alert` 表

**修改文件**：`main.py`、`db.py`

## 2026-05-20

### 更新 9：安装本地 Playwright 渲染引擎，修复 fallback 路径

- **问题诊断**：
  1. 外部 t2i 渲染服务（t2i.soulter.top）当前返回 502，完全不可用
  2. `_html_to_pic` fallback 中 `page.set_content(base_url=...)` 参数错误（Playwright 的 `set_content` 不接受 `base_url`，应传给 `browser.new_page`）
- **修复**：
  - 在 Docker 容器中安装 Playwright Python 包及 Chromium 浏览器二进制文件（含系统依赖库）
  - 修正 `_html_to_pic`：`base_url` 从 `set_content()` 移至 `browser.new_page(base_url=...)`，使本地相对路径资源（CSS、图片）能正确解析
  - 本地 Playwright fallback 渲染尺寸精确：706px 宽度 × 1.5 dsf = 1059px，无右侧空白，清晰度高
- **影响范围**：所有卡片渲染（网络服务故障时自动 fallback 到本地）

**修改文件**：`render_adapter.py`、Docker 容器环境

## 2026-05-20

### 更新 8：裁剪右侧空白并统一优化所有卡片渲染

- **问题诊断**：
  1. 外部 t2i 渲染服务使用固定 viewport 宽度（约 1280px），与卡片实际 CSS 宽度（706px 等）不匹配，导致截图右侧出现大量空白
  2. 服务对 `deviceScaleFactor` 参数响应不一致，无法通过固定公式计算裁剪尺寸
- **修复**：
  - 新增 `_crop_image()` 函数（基于 Pillow），在获取渲染图片后自动裁剪右侧空白
  - 裁剪策略：优先从 HTML 中提取固定 CSS 高度（如 `h-[1160px]`）推断实际 `device_scale_factor`；对 `h-auto` 模板使用宽度启发式推断
  - 仅在图片实际宽度明显大于目标宽度（>30px）时才执行裁剪，避免误裁
  - `_try_star_html_render()` 中所有返回路径（URL 下载、file://、本地路径）均统一经过裁剪处理
- **影响范围**：所有卡片渲染（arkcard、efcard、rogue、rogue_info、clue、gacha、ef_gacha）

**修改文件**：`render_adapter.py`

## 2026-05-20

### 更新 7：修复 arkcard 渲染质量问题

- **问题诊断**：
  1. AstrBot 的 `html_render` 走网络策略，POST 到外部渲染服务，默认 `quality=40` 的 JPEG，导致模糊
  2. 外部渲染服务无法访问本地 `file://` 资源（字体、图片），导致元素缺失
  3. `_html_to_pic` fallback 中 `viewport.height=1` 导致布局计算异常
- **修复**：
  - 调用 `star.html_render` 时传递 `options={"type": "png", "quality": 100}`，覆盖默认低质量 JPEG
  - 新增 `_inline_resources()` 函数，将本地图片、字体等资源内联为 base64 data URL，确保外部服务能正确渲染
  - `_html_to_pic` fallback：增大初始 viewport 高度、等待布局稳定、动态调整 viewport 匹配内容尺寸
- **影响范围**：所有卡片渲染（arkcard、efcard、rogue、clue、gacha）

**修改文件**：`render_adapter.py`

## 2026-05-20

### 更新 6：渲染功能补齐与质量优化

- **补齐缺失渲染函数**：新增 `render_rogue_card`、`render_rogue_info`、`render_clue_board`、`render_gacha_history`、`render_ef_gacha_history`，覆盖原 NoneBot 插件全部渲染能力
- **修复渲染质量问题**：
  - 添加 `base_url` 参数，解决模板中相对路径资源（CSS、图片）加载失败的问题
  - 添加 `device_scale_factor=1.5`，提升输出图片清晰度（HiDPI）
  - 高度改为自适应（`height=1` + `full_page=True`），解决内容截断或空白过多问题
- **补齐 Jinja2 过滤器**：添加 `charId_to_avatarUrl`、`charId_to_portraitUrl`、`ef_charId_to_avatarUrl`、`format_timestamp_str`、`format_timestamp_md`、`loads_json`，供肉鸽/抽卡模板使用
- **新增肉鸽命令**：
  - `/sk rogue [主题名]` — 查询肉鸽战绩并渲染卡片（支持傀影/水月/萨米/萨卡兹/界园）
  - `/sk rginfo [记录ID] [--favored]` — 查询肉鸽战绩详情
- **新增抽卡命令占位**：`/sk gacha`、`/sk efgacha`（依赖数据库模型尚未移植，标记为开发中）

**修改文件**：`render_adapter.py`、`filters.py`、`main.py`

## 2026-05-19

### 更新 5：新增森空岛 COS 图片功能

- 新增 `/sk cos [角色名]` 命令，支持获取森空岛社区 COS 图片
- 不带角色名时从 cosplay 标签（tagId=451）随机获取
- 带角色名时通过标签搜索匹配，支持标签缓存持久化
- 新增 `skland_cos.py` 模块，封装社区 web v1 API（`tag/index`、`tag` 搜索）
- 图片下载到本地临时文件后返回，兼容各平台适配器

**修改文件**：`skland_cos.py`、`main.py`

## 更早的更新

### 更新 1：文本格式与命令增强

- 统一游戏名称标签：`【终末地】`→`[EndField]`，`【明日方舟】`→`[Arknights]`
- 全角符号转半角，时间单位统一为 `h/m`
- 移除剩余时间后的解释文本（如 `后全部完成`）
- 新增 `/sk sign` 联合签到命令（同时签到 Ark + EF）
- 所有 `/sk` 命令回复统一添加 `[Sklands]\n` 前缀，便于外部插件识别

**修改文件**：`main.py`、`filters.py`

### 更新 2：卡片渲染功能启用与稳定性修复

- 启用 `/sk arkcard` 与 `/sk efcard` 卡片渲染
- 新增 `render_adapter.py` 渲染适配层，支持 AstrBot `html_render` 与 Playwright fallback 双通道
- 修复 `html_render` 返回 `file://` 或 `http` URL 时无法正确加载图片的问题
- 添加 `event.stop_event()` 阻止 LLM 对 `/sk` 命令的后续回复
- 渲染前添加"正在渲染卡片，请稍候..."提示，避免用户感知无响应

**修改文件**：`main.py`、`render_adapter.py`、`.gitignore`、`.gitattributes`

### 更新 3：修复远程安装后插件消失问题

- 新增 `requirements.txt`，声明所有第三方依赖（`sqlalchemy`、`aiosqlite`、`httpx`、`pydantic`、`qrcode`、`jinja2`、`rich`、`playwright`）
- 根因：远程服务器缺少依赖时 `main.py` 导入失败，AstrBot 将插件打入失败列表，表现为"安装后消失"

**修改文件**：`requirements.txt`

### 更新 4：修复 metadata.yaml 仓库地址错误

- 修复 `metadata.yaml` 中 `repo` 字段指向原始 nonebot 仓库的问题，改为指向正确的 AstrBot 移植仓库 `SciNancy/astrbot_plugin_sklands`
- 根因：AstrBot 安装插件时从 `repo` 地址拉取代码，错误地址导致下载了 nonebot 版本（无 `main.py`），插件完全无法加载

**修改文件**：`metadata.yaml`

## 2026-05-20

### 更新 7：修复 COS 功能并增强体验

- **重写 `skland_cos.py`**：修复 COS 图片获取失败问题
  - 根因：原代码使用游戏 API（`api/v1`）的签名方式调用社区 API（`web/v1`），认证完全不匹配
  - 解决：参考 `nonebot-plugin-skland-cos` 实现，改用社区 API 独立认证流程
    1. 先调 `/web/v1/auth/refresh` 用 `cred` 获取 `sign token`
    2. 用 `sign token` + 时间戳 + `dId` 生成签名
    3. 请求 header 携带 `cred`、`sign`、`timestamp`、`platform`、`vName`、`dId`
  - 修正参数名：`tagId`（原错误为 `id`），新增 `sortType`、`pageSize`、`listId`、`gameId`
  - 修正图片字段：`item.imageListSlice[].url`（原错误地从 `post.images` / `content.blocks` 提取）
- **解决图片模糊问题**：新增 `_get_hd_url()` 函数，自动去除阿里云 OSS / 七牛云 / 腾讯云等 CDN 缩略图参数（`x-oss-process`、`imageView2`、`imageMogr2` 等），还原高清原图
- **图片附带帖子链接**：`fetch_cos_images` 返回 `list[dict]`，每项包含 `url` / `post_url` / `title`；发送图片后自动跟一条 `来源: https://www.skland.com/article?id=xxx`
- **新增 `feed/index` 回退**：关键词搜索时若 tag 未命中，回落到同人板块 feed 按标题匹配

**修改文件**：`skland_cos.py`（完全重写）、`main.py`
