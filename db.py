"""自携数据库封装（SQLAlchemy + aiosqlite）

AstrBot 只提供简单 KV 存储，无法满足关系型查询需求。
这里自携 SQLAlchemy + aiosqlite，完全独立于框架。
"""

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Text, Boolean, select

Base = declarative_base()


class SkUser(Base):
    """森空岛用户表"""
    __tablename__ = "skland_user"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 跨平台用户标识（如 "qq:123456" 或 "telegram:987654"）
    platform_user_id: Mapped[str] = mapped_column(Text, unique=True)
    # 森空岛用户ID（API用，非平台ID）
    user_id: Mapped[str] = mapped_column(Text, nullable=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=True)
    cred: Mapped[str] = mapped_column(Text)
    cred_token: Mapped[str] = mapped_column(Text)


class Character(Base):
    """绑定的游戏角色表"""
    __tablename__ = "skland_characters"
    # 关联用户ID + 角色UID 组成复合主键
    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(primary_key=True)
    role_id: Mapped[str] = mapped_column(String, nullable=True)
    app_code: Mapped[str] = mapped_column(Text)
    channel_master_id: Mapped[str] = mapped_column(Text)
    nickname: Mapped[str] = mapped_column(Text)
    isdefault: Mapped[bool] = mapped_column(default=False)


# 模块级单例：避免重复创建引擎
_engine = None
_session_maker = None

# 默认数据库路径（AstrBot 插件规范目录）
_DEFAULT_DB_PATH = str(Path("data/plugin_data/astrbot-plugin-skland") / "skland.db")


async def init_db(db_path: str = None, force: bool = False):
    """初始化数据库连接并创建表（幂等，但检测文件是否被删除）
    
    Args:
        db_path: 数据库文件路径，默认为 data/plugin_data/astrbot-plugin-skland/skland.db
        force: 强制重新初始化（用于数据库文件被删除后重建）
    """
    global _engine, _session_maker
    
    path = db_path or _DEFAULT_DB_PATH
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    # 如果引擎已存在，检查数据库文件是否还存在
    # 用户可能通过 rm 删除了数据库文件，但 _engine 仍然缓存着旧连接
    if _engine is not None and not force:
        if not path_obj.exists():
            # 数据库文件被删除了，需要强制重新初始化
            logger.info("[Skland] 检测到数据库文件缺失，重新初始化数据库...")
            force = True
        else:
            # 一切正常，复用现有连接
            return
    
    if _engine is not None and force:
        # 释放旧引擎的资源
        await _engine.dispose()
        _engine = None
        _session_maker = None
    
    if _engine is None:
        _engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _session_maker = async_sessionmaker(_engine, expire_on_commit=False)
        logger.info(f"[Skland] 数据库已初始化: {path}")


async def get_session() -> AsyncSession:
    """获取异步数据库会话（惰性初始化，首次调用时自动创建数据库）"""
    global _session_maker
    if _session_maker is None:
        await init_db()
    return _session_maker()


async def get_user_by_platform(session: AsyncSession, platform_user_id: str) -> SkUser | None:
    """通过跨平台用户ID查询用户"""
    result = await session.execute(
        select(SkUser).where(SkUser.platform_user_id == platform_user_id)
    )
    return result.scalar_one_or_none()


async def get_default_ark_character(session: AsyncSession, user: SkUser) -> Character | None:
    """获取用户默认绑定的明日方舟角色"""
    result = await session.execute(
        select(Character).where(
            Character.id == user.id,
            Character.isdefault == True,
            Character.app_code == "arknights"
        )
    )
    return result.scalar_one_or_none()


async def get_default_ef_character(session: AsyncSession, user: SkUser) -> Character | None:
    """获取用户默认绑定的终末地角色"""
    result = await session.execute(
        select(Character).where(
            Character.id == user.id,
            Character.isdefault == True,
            Character.app_code == "endfield"
        )
    )
    return result.scalar_one_or_none()


async def get_ark_characters(session: AsyncSession, user: SkUser) -> list[Character]:
    """获取用户绑定的所有明日方舟角色"""
    result = await session.execute(
        select(Character).where(
            Character.id == user.id,
            Character.app_code == "arknights"
        )
    )
    return list(result.scalars().all())


async def get_ef_characters(session: AsyncSession, user: SkUser) -> list[Character]:
    """获取用户绑定的所有终末地角色"""
    result = await session.execute(
        select(Character).where(
            Character.id == user.id,
            Character.app_code == "endfield"
        )
    )
    return list(result.scalars().all())
