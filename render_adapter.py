"""渲染适配层：将原插件的 Jinja2 模板渲染为图片

原插件使用 nonebot-plugin-htmlrender 的 template_to_pic（基于 Playwright）。
AstrBot 也可能提供 html_render（基于 Playwright）。

本模块优先使用 AstrBot 的 html_render，如果不可用则使用内置 Playwright fallback。
"""

import jinja2
from pathlib import Path
from datetime import datetime

from .schemas import (
    ArkCard,
    EndfieldCard,
    RogueData,
    Clue,
    GroupedGachaRecord,
    EfGroupedGachaRecord,
    Status,
    PlayerBase,
)
from .config import RES_DIR, TEMPLATES_DIR
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
    format_timestamp_str,
    format_timestamp_md,
    charId_to_avatarUrl,
    charId_to_portraitUrl,
    ef_charId_to_avatarUrl,
    loads_json,
)

# 创建带自定义过滤器的 Jinja2 环境（与原插件保持一致）
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    enable_async=True,
)

# 方舟/终末地卡片过滤器
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
# 肉鸽/抽卡过滤器
_jinja_env.filters["format_timestamp_str"] = format_timestamp_str
_jinja_env.filters["format_timestamp_md"] = format_timestamp_md
_jinja_env.filters["charId_to_avatarUrl"] = charId_to_avatarUrl
_jinja_env.filters["charId_to_portraitUrl"] = charId_to_portraitUrl
_jinja_env.filters["ef_charId_to_avatarUrl"] = ef_charId_to_avatarUrl
_jinja_env.filters["loads_json"] = loads_json


def _make_width_clamp_style(width: int = 706) -> str:
    """生成强制页面宽度的注入样式（解决 viewport 无法设置的问题）"""
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


async def _html_to_pic(
    html_content: str,
    width: int = 706,
    height: int = 1,
    full_page: bool = True,
    device_scale_factor: float = 1.5,
    base_url: str | None = None,
) -> str:
    """使用 Playwright 将 HTML 渲染为图片，返回图片路径。

    作为 AstrBot html_render 的 fallback，当 star.html_render 不可用时调用。

    Args:
        html_content: HTML 内容
        width: 视口宽度（默认 706）
        height: 视口高度（默认 1 表示自适应）
        full_page: 是否截取全页面（默认 True）
        device_scale_factor: 设备缩放因子（默认 1.5，提高清晰度）
        base_url: 基础 URL，用于解析相对路径资源
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright 未安装，无法渲染卡片。"
            "请运行: pip install playwright && playwright install chromium"
        )

    output_path = Path(__file__).parent / "data" / "cache"
    output_path.mkdir(parents=True, exist_ok=True)
    file_name = output_path / f"skland_card_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            viewport={"width": width, "height": max(height, 1)},
            device_scale_factor=device_scale_factor,
        )
        # 设置 base_url，让模板中的相对路径资源（CSS、图片）能正确加载
        await page.set_content(
            html_content,
            wait_until="networkidle",
            base_url=base_url or f"file://{TEMPLATES_DIR}",
        )
        await page.screenshot(
            path=str(file_name),
            full_page=full_page,
        )
        await browser.close()

    return str(file_name)


async def _try_star_html_render(
    star,
    html_content: str,
    width: int = 706,
    height: int = 1,
    full_page: bool = True,
    device_scale_factor: float = 1.5,
    base_url: str | None = None,
) -> str:
    """优先尝试 AstrBot 的 html_render，失败则使用内置 Playwright fallback。

    返回值始终是本地文件路径（因为 event.image_result 需要路径）。
    """
    import logging

    logger = logging.getLogger("astrbot")

    # 检查 star 是否有 html_render 方法
    if hasattr(star, "html_render"):
        try:
            wrapper = "{{ html | safe }}"
            # 尝试传递额外的渲染参数（部分 AstrBot 版本支持）
            url = await star.html_render(wrapper, {"html": html_content})
            logger.debug(f"[Skland] html_render 返回: {url}")
            # 如果返回的是本地路径或 file:// 协议，转换为纯路径
            if url.startswith("file://"):
                return url[7:]
            if url.startswith("http"):
                # URL 形式，下载到本地缓存后返回路径
                logger.info(f"[Skland] html_render 返回 URL，正在下载图片...")
                import httpx

                async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    output_path = Path(__file__).parent / "data" / "cache"
                    output_path.mkdir(parents=True, exist_ok=True)
                    file_name = (
                        output_path
                        / f"skland_card_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
                    )
                    file_name.write_bytes(resp.content)
                    logger.info(f"[Skland] 图片下载完成: {file_name}")
                    return str(file_name)
            else:
                # 假设是本地路径
                return url
        except Exception as e:
            logger.warning(f"[Skland] html_render 失败，使用 Playwright fallback: {e}")

    return await _html_to_pic(
        html_content,
        width=width,
        height=height,
        full_page=full_page,
        device_scale_factor=device_scale_factor,
        base_url=base_url,
    )


# ==================== 方舟卡片 ====================


async def render_ark_card(star, card_data: ArkCard, bg_path: str) -> str:
    """渲染明日方舟角色卡片为图片路径"""
    import logging

    logger = logging.getLogger("astrbot")

    logger.debug("[Skland] 开始渲染方舟卡片模板...")
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
    logger.debug("[Skland] 模板渲染完成")

    width_clamp = _make_width_clamp_style(706)
    if "</head>" in rendered_html:
        rendered_html = rendered_html.replace("</head>", width_clamp + "</head>")
    else:
        rendered_html = width_clamp + rendered_html

    logger.debug("[Skland] 开始截图渲染...")
    result = await _try_star_html_render(
        star,
        rendered_html,
        width=706,
        height=1,  # 自适应高度，与原插件一致
        full_page=True,
        device_scale_factor=1.5,
        base_url=f"file://{TEMPLATES_DIR}",
    )
    logger.debug(f"[Skland] 截图完成: {result}")
    return result


# ==================== 终末地卡片 ====================


async def render_ef_card(
    star,
    card_data: EndfieldCard,
    bg_path: str,
    show_all: bool = False,
    is_simple: bool = False,
) -> str:
    """渲染终末地角色卡片为图片路径"""
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

    simple_bg = str(RES_DIR / "images" / "background" / "endfield" / "simple" / "simple_bg.png")
    simple_bg_top = str(
        RES_DIR / "images" / "background" / "endfield" / "simple" / "simple_bg_top.png"
    )

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

    return await _try_star_html_render(
        star,
        rendered_html,
        width=706,
        height=1,  # 自适应高度，与原插件一致
        full_page=True,
        device_scale_factor=1.5,
        base_url=f"file://{TEMPLATES_DIR}",
    )


# ==================== 肉鸽战绩 ====================


async def render_rogue_card(star, card_data: RogueData, bg_path: str) -> str:
    """渲染明日方舟肉鸽战绩卡片为图片路径"""
    template = _jinja_env.get_template("rogue.html.jinja2")

    rendered_html = await template.render_async(
        background_image=bg_path,
        topic_img=card_data.topic_img,
        topic=card_data.topic,
        now_ts=datetime.now().timestamp(),
        career=card_data.career,
        game_user_info=card_data.gameUserInfo,
        history=card_data.history,
    )

    width_clamp = _make_width_clamp_style(2200)
    if "</head>" in rendered_html:
        rendered_html = rendered_html.replace("</head>", width_clamp + "</head>")
    else:
        rendered_html = width_clamp + rendered_html

    return await _try_star_html_render(
        star,
        rendered_html,
        width=2200,
        height=1,
        full_page=True,
        device_scale_factor=1.5,
        base_url=f"file://{TEMPLATES_DIR}",
    )


async def render_rogue_info(
    star, card_data: RogueData, bg_path: str, record_id: int, is_favored: bool
) -> str:
    """渲染明日方舟肉鸽战绩详情为图片路径"""
    template = _jinja_env.get_template("rogue_info.html.jinja2")

    # 获取指定记录
    if is_favored and record_id - 1 < len(card_data.history.favourRecords):
        record = card_data.history.favourRecords[record_id - 1]
    elif record_id - 1 < len(card_data.history.records):
        record = card_data.history.records[record_id - 1]
    else:
        record = None

    rendered_html = await template.render_async(
        id=record_id,
        record=record,
        is_favored=is_favored,
        background_image=bg_path,
        topic_img=card_data.topic_img,
        topic=card_data.topic,
        now_ts=datetime.now().timestamp(),
        career=card_data.career,
        game_user_info=card_data.gameUserInfo,
        history=card_data.history,
    )

    width_clamp = _make_width_clamp_style(1100)
    if "</head>" in rendered_html:
        rendered_html = rendered_html.replace("</head>", width_clamp + "</head>")
    else:
        rendered_html = width_clamp + rendered_html

    return await _try_star_html_render(
        star,
        rendered_html,
        width=1100,
        height=1,
        full_page=True,
        device_scale_factor=1.5,
        base_url=f"file://{TEMPLATES_DIR}",
    )


# ==================== 线索看板 ====================


async def render_clue_board(star, clue_data: Clue) -> str:
    """渲染线索看板为图片路径"""
    template = _jinja_env.get_template("clue.html.jinja2")

    rendered_html = await template.render_async(clue=clue_data)

    width_clamp = _make_width_clamp_style(1100)
    if "</head>" in rendered_html:
        rendered_html = rendered_html.replace("</head>", width_clamp + "</head>")
    else:
        rendered_html = width_clamp + rendered_html

    return await _try_star_html_render(
        star,
        rendered_html,
        width=1100,
        height=1,
        full_page=True,
        device_scale_factor=1.5,
        base_url=f"file://{TEMPLATES_DIR}",
    )


# ==================== 抽卡记录 ====================


async def render_gacha_history(
    star,
    record: GroupedGachaRecord,
    char,
    status: Status,
    begin: int | None = None,
    limit: int | None = None,
) -> str:
    """渲染明日方舟抽卡记录为图片路径"""
    template = _jinja_env.get_template("gacha.html.jinja2")

    rendered_html = await template.render_async(
        record=record,
        character=char,
        status=status,
        start_index=begin,
        end_index=limit,
    )

    width_clamp = _make_width_clamp_style(720)
    if "</head>" in rendered_html:
        rendered_html = rendered_html.replace("</head>", width_clamp + "</head>")
    else:
        rendered_html = width_clamp + rendered_html

    return await _try_star_html_render(
        star,
        rendered_html,
        width=720,
        height=1,
        full_page=True,
        device_scale_factor=1.5,
        base_url=f"file://{TEMPLATES_DIR}",
    )


async def render_ef_gacha_history(
    star,
    record: EfGroupedGachaRecord,
    player: PlayerBase,
    char,
    begin: int | None = None,
    limit: int | None = None,
) -> str:
    """渲染终末地抽卡记录为图片路径"""
    template = _jinja_env.get_template("ef_gacha.html.jinja2")

    rendered_html = await template.render_async(
        avatar_url=player.avatarUrl,
        record=record,
        character=char,
        start_index=begin,
        end_index=limit,
    )

    width_clamp = _make_width_clamp_style(800)
    if "</head>" in rendered_html:
        rendered_html = rendered_html.replace("</head>", width_clamp + "</head>")
    else:
        rendered_html = width_clamp + rendered_html

    return await _try_star_html_render(
        star,
        rendered_html,
        width=800,
        height=1,
        full_page=True,
        device_scale_factor=1.5,
        base_url=f"file://{TEMPLATES_DIR}",
    )
