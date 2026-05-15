# AstrBot 森空岛插件

AstrBot 平台的森空岛（Skland）插件，支持明日方舟和明日方舟：终末地的角色管理、签到和看板查询。

## 功能

- **账号绑定**：通过扫码登录绑定森空岛账号
- **角色同步**：自动同步绑定的游戏角色
- **签到**：
  - `/sk arksign` - 明日方舟每日签到（支持多角色）
  - `/sk efsign` - 终末地每日签到（支持多角色）
- **看板查询**：
  - `/sk arkmr` - 明日方舟纯文本看板
  - `/sk efmr` - 终末地纯文本看板
  - `/sk mr` - 合并看板（同时显示两款游戏）
- **数据同步**：`/sk sync` - 手动同步角色绑定列表

## 安装

在 AstrBot 的 WebUI 插件市场中搜索 `astrbot_plugin_sklands` 并安装，或手动克隆到插件目录：

```bash
cd AstrBot/data/plugins/
git clone https://github.com/SciNancy/astrbot_plugin_sklands.git
```

重启 AstrBot 即可加载。

## 使用

1. **绑定账号**：发送 `/sk login`，按提示扫码登录
2. **查看看板**：`/sk arkmr` 或 `/sk efmr`
3. **每日签到**：`/sk arksign` 或 `/sk efsign`
4. **查看帮助**：`/sk help`

## 指令列表

| 指令 | 说明 |
|------|------|
| `/sk login` | 扫码绑定森空岛账号 |
| `/sk sync` | 手动同步角色绑定 |
| `/sk arksign` | 明日方舟签到 |
| `/sk efsign` | 终末地签到 |
| `/sk arkmr` | 明日方舟看板 |
| `/sk efmr` | 终末地看板 |
| `/sk mr` | 合并看板 |
| `/sk help` | 显示帮助 |

## 平台适配

本插件基于 AstrBot 框架开发，支持所有 AstrBot 适配的平台（QQ、WebUI、微信等）。纯文本输出格式在各平台间通用。

## 注意事项

- 首次使用需要先绑定森空岛账号
- Token 会自动刷新，失效时会提示重新登录
- 数据库文件存储在插件目录下，删除后需重新绑定

## 技术说明

- 基于 AstrBot v4.x 插件架构
- 使用 SQLAlchemy + aiosqlite 进行数据持久化
- 异步 HTTP 客户端访问森空岛 API
- 纯文本输出，无需前端渲染依赖

## License

MIT

## 致谢

移植自 [nonebot-plugin-skland](https://github.com/GuGuMur/nonebot-plugin-skland)，感谢原作者的工作。
