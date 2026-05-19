# Changelog

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
