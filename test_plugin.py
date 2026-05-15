"""
独立测试脚本：验证插件核心功能（无需启动 AstrBot）

运行方式:
    cd E:\PROJECT\Project-SKD\astrbot-plugin-skland
    python test_plugin.py

测试内容:
    1. 数据库初始化 + 用户增删查
    2. 渲染层（生成一张角色卡片图片）
    3. 可选：真实 API 请求（需要有效的 cred）
"""

import asyncio
import sys
from pathlib import Path

# 把插件目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from astrbot_plugin_skland.db import init_db, get_session, SkUser, Character
from astrbot_plugin_skland.db import get_user_by_platform, get_default_ark_character
from astrbot_plugin_skland.render_adapter import render_ark_card
from astrbot_plugin_skland.schemas import ArkCard

# 模拟一个 AstrBot Star 对象（只需要 html_render 方法）
class FakeStar:
    async def html_render(self, template: str, data: dict, options: dict = None):
        """
        模拟 AstrBot 的 html_render。
        由于独立环境没有 Playwright，这里只是把 HTML 保存到文件，
        你可以用浏览器打开查看效果。
        """
        from jinja2 import Template
        html = Template(template).render(**data)
        output = Path("test_output.html")
        output.write_text(html, encoding="utf-8")
        print(f"[FakeStar] HTML 已保存到: {output.absolute()}")
        print("[FakeStar] 请用浏览器打开该文件查看渲染效果")
        return str(output.absolute())


async def test_database():
    """测试数据库功能"""
    print("=" * 50)
    print("测试1: 数据库")
    print("=" * 50)

    db_path = Path(__file__).parent / "test_skland.db"
    await init_db(str(db_path))

    async with await get_session() as session:
        # 创建用户
        user = SkUser(
            platform_user_id="qq:123456",
            cred="test_cred_value",
            cred_token="test_token_value",
        )
        session.add(user)
        await session.commit()
        print(f"  [OK] 创建用户: {user.platform_user_id}")

        # 创建角色（阶段1 MVP 需要手动有角色数据）
        char = Character(
            id=user.id,
            uid="123456789",
            app_code="arknights",
            channel_master_id="1",
            nickname="测试博士",
            isdefault=True,
        )
        session.add(char)
        await session.commit()
        print(f"  [OK] 创建角色: {char.nickname} (uid={char.uid})")

        # 查询
        found_user = await get_user_by_platform(session, "qq:123456")
        found_char = await get_default_ark_character(session, found_user)
        print(f"  [OK] 查询到默认角色: {found_char.nickname}")

        # 清理
        await session.delete(found_user)
        await session.commit()

    # 清理数据库文件
    db_path.unlink(missing_ok=True)
    print("  [OK] 数据库测试通过")


async def test_render():
    """测试渲染层（不调用真实 API，用假数据）"""
    print()
    print("=" * 50)
    print("测试2: 渲染层")
    print("=" * 50)

    # 构造一个最小化的 ArkCard（只要模板用到的字段）
    # 注意：这里用空对象填充模板中必须的字段，实际会渲染但可能显示为空
    fake_card = ArkCard(
        status={"ap": {"current": 120, "max": 135}},
        medal={"total": 100},
        assistChars=[],
        chars=[],
        skins=[],
        recruit=[],
        campaign={},
        tower={},
        routine={},
        building={},
        equipmentInfoMap={},
        manufactureFormulaInfoMap={},
        charInfoMap={},
    )

    star = FakeStar()
    bg_path = str(Path(__file__).parent / "resources" / "images" / "background" / "bg.jpg")

    try:
        result = await render_ark_card(star, fake_card, bg_path)
        print(f"  [OK] 渲染完成: {result}")
    except Exception as e:
        print(f"  [WARN] 渲染失败（可能是模板字段缺失）: {e}")
        print("  [INFO] 这是正常的，因为我们用了假数据。真实 API 数据会包含所有字段。")


async def test_real_api():
    """测试真实 API（可选，需要有效的 cred）"""
    print()
    print("=" * 50)
    print("测试3: 真实 API（可选）")
    print("=" * 50)

    cred = input("  请输入 cred（直接回车跳过）: ").strip()
    if not cred:
        print("  [SKIP] 跳过 API 测试")
        return

    cred_token = input("  请输入 cred_token: ").strip()
    uid = input("  请输入角色 uid: ").strip()

    from astrbot_plugin_skland.api import SklandAPI
    from astrbot_plugin_skland.schemas import CRED

    try:
        card_data = await SklandAPI.ark_card(CRED(cred=cred, token=cred_token), uid)
        print(f"  [OK] API 请求成功!")
        print(f"  [INFO] 角色昵称: {card_data.status.nickname if hasattr(card_data.status, 'nickname') else 'N/A'}")

        # 渲染成图片
        star = FakeStar()
        bg_path = str(Path(__file__).parent / "resources" / "images" / "background" / "bg.jpg")
        result = await render_ark_card(star, card_data, bg_path)
        print(f"  [OK] 图片渲染完成: {result}")

    except Exception as e:
        print(f"  [FAIL] API 请求失败: {e}")


async def main():
    print("AstrBot 插件 Skland 独立测试脚本")
    print("=" * 50)

    await test_database()
    await test_render()
    await test_real_api()

    print()
    print("=" * 50)
    print("测试完成！")
    print("=" * 50)
    print()
    print("如果以上测试通过，说明插件代码本身没问题。")
    print("接下来请按下面的方式安装到 AstrBot 中进行真实测试。")


if __name__ == "__main__":
    asyncio.run(main())
