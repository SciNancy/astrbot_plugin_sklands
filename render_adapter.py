"""渲染适配层：将原插件的 Jinja2 模板渲染桥接到 AstrBot 的 html_render

原插件使用 nonebot-plugin-htmlrender 的 template_to_pic，
AstrBot 原生提供 html_render（基于 Playwright）。

关键差异：
- 原插件支持设置 viewport，AstrBot 的 html_render 只透传 screenshot 参数
- 因此改用 CSS 强制页面宽度，让 Playwright 的 full_page 截图自动适配内容高度
"""

import jinja2
from pathlib import Path
from datetime import datetime

from .schemas import ArkCard, EndfieldCard
from .filters import (
    format_timestamp,
    time_to_next_4am,
    time_to_next_monday_4am,
    format_stamina_time,
    format_date_ymd,
    get_domain_info,
    get_rarity_color,
    get_equip_rarity_color,
    get_profession_icon,
    get_property_icon,
    format_money_wan,
)

# 模板目录
TEMPLATES_DIR = Path(__file__).parent / "resources" / "templates"

# 创建带自定义过滤器的 Jinja2 环境（与原插件保持一致）
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    enable_async=True,
)
_jinja_env.filters["format_timestamp"] = format_timestamp
_jinja_env.filters["time_to_next_4am"] = time_to_next_4am
_jinja_env.filters["time_to_next_monday_4am"] = time_to_next_monday_4am
# 终末地卡片过滤器
_jinja_env.filters["format_stamina_time"] = format_stamina_time
_jinja_env.filters["format_date_ymd"] = format_date_ymd
_jinja_env.filters["get_domain_info"] = get_domain_info
_jinja_env.filters["get_rarity_color"] = get_rarity_color
_jinja_env.filters["get_equip_rarity_color"] = get_equip_rarity_color
_jinja_env.filters["get_profession_icon"] = get_profession_icon
_jinja_env.filters["get_property_icon"] = get_property_icon
_jinja_env.filters["format_money_wan"] = format_money_wan


def _make_width_clamp_style(width: int = 706) -> str:
    """生成强制页面宽度的注入样式（解决 AstrBot html_render 无法设置 viewport 的问题）"""
    return f"""
<style id="astrbot-render-fix">
  html, body {{
    width: {width}px !important;
    min-width: {width}px !important;
    max-width: {width}px !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow-x: hidden !important;
  }}
</style>
"""


async def render_ark_card(star, card_data: ArkCard, bg_path: str) -> str:
    """渲染明日方舟角色卡片为图片 URL"""
    template = _jinja_env.get_template("ark_card.html.jinja2")

    rendered_html = await template.render_async(
        now_ts=datetime.now().timestamp(),
        background_image=bg_path,
        status=card_data.status,
        employed_chars=len(card_data.chars),
        skins=len(card_data.skins),
        building=card_data.building,
        medals=card_data.medal.total,
        assist_chars=card_data.assistChars,
        recruit_finished=card_data.recruit_finished,
        recruit_max=len(card_data.recruit),
        recruit_complete_time=card_data.recruit_complete_time,
        campaign=card_data.campaign,
        routine=card_data.routine,
        tower=card_data.tower,
        training_char=card_data.trainee_char,
    )

    width_clamp = _make_width_clamp_style(706)
    if "</head>" in rendered_html:
        rendered_html = rendered_html.replace("</head>", width_clamp + "</head>")
    else:
        rendered_html = width_clamp + rendered_html

    wrapper = "{{ html | safe }}"
    url = await star.html_render(wrapper, {"html": rendered_html})
    return url


async def render_ef_card(star, card_data: EndfieldCard, bg_path: str, show_all: bool = False, is_simple: bool = False) -> str:
    """渲染终末地角色卡片为图片 URL"""
    if show_all:
        filtered_chars = card_data.chars
    else:
        char_map = {char.charData.id: char for char in card_data.chars}
        filtered_chars = [char_map[cid] for cid in card_data.config.charIds if cid in char_map]

    control_center_level = 0
    for room in card_data.spaceShip.rooms:
        if room.type == 0:
            control_center_level = room.level
            break

    total_trchest_count = sum(
        collection.trchestCount
        for domain in card_data.domain
        for collection in domain.collections
    )
    total_puzzle_count = sum(
        collection.puzzleCount
        for domain in card_data.domain
        for collection in domain.collections
    )

    current_ts = float(card_data.currentTs) if card_data.currentTs else datetime.now().timestamp()
    max_ts = float(card_data.dungeon.maxTs) if card_data.dungeon.maxTs else current_ts
    stamina_remaining_seconds = max(0, max_ts - current_ts)

    cur_stamina = int(card_data.dungeon.curStamina) if card_data.dungeon.curStamina else 0
    max_stamina = int(card_data.dungeon.maxStamina) if card_data.dungeon.maxStamina else 1
    stamina_percent = min(100, (cur_stamina / max_stamina) * 100) if max_stamina > 0 else 0

    from .config import RES_DIR
    simple_bg = str(RES_DIR / "images" / "background" / "endfield" / "simple" / "simple_bg.png")
    simple_bg_top = str(RES_DIR / "images" / "background" / "endfield" / "simple" / "simple_bg_top.png")

    template = _jinja_env.get_template("endfield_card.html.jinja2")

    rendered_html = await template.render_async(
        now_ts=datetime.now().timestamp(),
        background_image=bg_path,
        simple_bg_enabled=is_simple,
        simple_bg=simple_bg,
        simple_bg_top=simple_bg_top,
        chars=filtered_chars,
        base=card_data.base,
        dungeon=card_data.dungeon,
        bpSystem=card_data.bpSystem,
        dailyMission=card_data.dailyMission,
        weeklyMission=card_data.weeklyMission,
        achieve=card_data.achieve,
        domain=card_data.domain,
        control_center_level=control_center_level,
        total_trchest_count=total_trchest_count,
        total_puzzle_count=total_puzzle_count,
        stamina_remaining_seconds=stamina_remaining_seconds,
        stamina_percent=stamina_percent,
    )

    width_clamp = _make_width_clamp_style(706)
    if "</head>" in rendered_html:
        rendered_html = rendered_html.replace("</head>", width_clamp + "</head>")
    else:
        rendered_html = width_clamp + rendered_html

    wrapper = "{{ html | safe }}"
    url = await star.html_render(wrapper, {"html": rendered_html})
    return url
