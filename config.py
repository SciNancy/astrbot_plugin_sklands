"""最小化配置模块，兼容原插件 filters.py 的路径依赖"""

from pathlib import Path

# 插件数据目录（AstrBot 规范：data/plugin_data/{plugin_name}/）
DATA_DIR = Path("data/plugin_data/astrbot-plugin-skland")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 缓存目录（下载的游戏资源、临时文件）
CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 资源目录（模板、字体、静态图片）
RES_DIR = Path(__file__).parent / "resources"
TEMPLATES_DIR = RES_DIR / "templates"
