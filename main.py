"""AstrBot 插件入口：森空岛（Skland）

指令前缀改为 /sk，新增纯文本看板功能
"""

import asyncio
import math
from pathlib import Path
from datetime import datetime

import qrcode
import astrbot.api.message_components as Comp
from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star
from astrbot.api import logger

from .db import (
    init_db,
    get_session,
    SkUser,
    Character,
    get_user_by_platform,
    get_default_ark_character,
    get_default_ef_character,
    get_ark_characters,
    get_ef_characters,
)
from .api import SklandAPI, SklandLoginAPI
from .schemas import CRED
# Card 渲染功能（暂未发布）
# from .render_adapter import render_ark_card, render_ef_card
from .utils import call_api_with_refresh


class SklandPlugin(Star):
    """森空岛插件：查询鹰角网络旗下游戏数据"""

    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = Path("data/plugin_data/astrbot-plugin-skland")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "skland.db"
        self._qrcode_tasks: dict[str, dict] = {}

    @filter.on_astrbot_loaded()
    async def on_loaded(self):
        await init_db(str(self.db_path))
        logger.info("[Skland] 插件已加载，数据库就绪")

    @staticmethod
    def _format_error(e: Exception) -> str:
        """格式化异常为友好的错误消息

        区分 Token 失效和其他错误，Token 失效时提示重新登录
        """
        from .exception import LoginException, UnauthorizedException

        msg = str(e)
        if isinstance(e, (LoginException, UnauthorizedException)):
            if "Token 已失效" in msg:
                return msg  # 已经包含提示
            return f"Token 已失效，请使用 /sk login 重新扫码绑定。\n原始错误: {msg}"
        elif isinstance(e, Exception):
            return f"请求失败: {msg}"
        return f"未知错误: {msg}"

    # ==================== 指令组 ====================

    @filter.command_group("sk")
    def sk(self):
        """森空岛主指令组"""
        pass

    # ==================== 绑定相关 ====================

    @sk.command("login")
    async def cmd_login(self, event: AstrMessageEvent):
        """扫码绑定森空岛账号（推荐） 用法: /sk login"""
        sender_id = event.get_sender_id()
        umo = event.unified_msg_origin

        try:
            scan_id = await SklandLoginAPI.get_scan()
        except Exception as e:
            yield event.plain_result(f"❌ 获取二维码失败: {e}")
            return

        try:
            scan_url = f"hypergryph://scan_login?scanId={scan_id}"
            qr_img = qrcode.make(scan_url)
            qr_path = self.data_dir / f"qrcode_{sender_id}.png"
            qr_img.save(str(qr_path))
        except Exception as e:
            yield event.plain_result(f"❌ 生成二维码失败: {e}")
            return

        yield event.plain_result(
            "请使用【森空岛APP】扫描下方二维码完成绑定\n"
            "二维码有效期约2分钟"
        )
        yield event.image_result(str(qr_path))

        self._qrcode_tasks[scan_id] = {"umo": umo, "sender_id": sender_id}
        asyncio.create_task(self._poll_scan_status(scan_id))

    async def _poll_scan_status(self, scan_id: str):
        task_info = self._qrcode_tasks.get(scan_id)
        if not task_info:
            return
        umo = task_info["umo"]
        sender_id = task_info["sender_id"]

        for i in range(40):
            await asyncio.sleep(3)
            try:
                scan_code = await SklandLoginAPI.get_scan_status(scan_id)
                if not scan_code:
                    continue

                token = await SklandLoginAPI.get_token_by_scan_code(scan_code)
                grant_code = await SklandLoginAPI.get_grant_code(token, 0)
                cred_data = await SklandLoginAPI.get_cred(grant_code)

                skland_user_id = None
                try:
                    skland_user_id = await SklandAPI.get_user_ID(cred_data)
                except Exception:
                    pass

                async with await get_session() as session:
                    existing = await get_user_by_platform(session, sender_id)
                    if existing:
                        existing.cred = cred_data.cred
                        existing.cred_token = cred_data.token
                        existing.access_token = token
                        if skland_user_id:
                            existing.user_id = skland_user_id
                        user = existing
                    else:
                        user = SkUser(
                            platform_user_id=sender_id,
                            user_id=skland_user_id,
                            access_token=token,
                            cred=cred_data.cred,
                            cred_token=cred_data.token,
                        )
                        session.add(user)
                        await session.flush()

                    try:
                        binding_list = await SklandAPI.get_binding(cred_data)
                        for app in binding_list:
                            for char in app.bindingList:
                                if char.roles:
                                    for role in char.roles:
                                        await session.merge(
                                            Character(
                                                id=user.id,
                                                uid=char.uid,
                                                role_id=role.roleId,
                                                nickname=role.nickname,
                                                app_code=app.appCode,
                                                channel_master_id=role.serverId,
                                                isdefault=len(char.roles) == 1 or role.isDefault,
                                            )
                                        )
                                else:
                                    await session.merge(
                                        Character(
                                            id=user.id,
                                            uid=char.uid,
                                            nickname=char.nickName,
                                            app_code=app.appCode,
                                            channel_master_id=char.channelMasterId,
                                            isdefault=len(app.bindingList) == 1 or char.isDefault,
                                        )
                                    )
                    except Exception as e:
                        logger.warning(f"[Skland] 自动拉取角色列表失败: {e}")

                    await session.commit()

                # 检查角色是否同步成功
                async with await get_session() as check_session:
                    user_check = await get_user_by_platform(check_session, sender_id)
                    ark_chars = await get_ark_characters(check_session, user_check) if user_check else []
                    ef_chars = await get_ef_characters(check_session, user_check) if user_check else []
                    has_chars = bool(ark_chars or ef_chars)

                if has_chars:
                    msg = "✅ 扫码绑定成功！"
                else:
                    msg = (
                        "✅ 扫码绑定成功！\n"
                        "⚠️ 但自动同步角色列表失败，请手动执行 /sk sync 同步游戏角色"
                    )
                chain = MessageChain()
                chain.chain = [Comp.Plain(msg)]
                await self.context.send_message(umo, chain)
                break

            except Exception as e:
                logger.debug(f"[Skland] 轮询中 ({i+1}/40): {e}")
                continue
        else:
            chain = MessageChain()
            chain.chain = [Comp.Plain("❌ 二维码已过期，请重新发送 /sk login")]
            await self.context.send_message(umo, chain)
        
        self._qrcode_tasks.pop(scan_id, None)

    @sk.command("bind")
    async def cmd_bind(self, event: AstrMessageEvent, cred: str, cred_token: str):
        """手动绑定  用法: /sk bind <cred> <cred_token>"""
        sender_id = event.get_sender_id()
        async with await get_session() as session:
            existing = await get_user_by_platform(session, sender_id)
            if existing:
                existing.cred = cred
                existing.cred_token = cred_token
                user = existing
            else:
                user = SkUser(platform_user_id=sender_id, cred=cred, cred_token=cred_token)
                session.add(user)
                await session.flush()

            try:
                cred_data = CRED(cred=cred, token=cred_token)
                skland_user_id = await SklandAPI.get_user_ID(cred_data)
                user.user_id = skland_user_id
            except Exception:
                pass

            await self._sync_binding_chars(session, user, CRED(cred=cred, token=cred_token))
            await session.commit()
            yield event.plain_result("绑定成功！")

    @sk.command("unbind")
    async def cmd_unbind(self, event: AstrMessageEvent):
        """解绑账号  用法: /sk unbind"""
        sender_id = event.get_sender_id()
        async with await get_session() as session:
            user = await get_user_by_platform(session, sender_id)
            if not user:
                yield event.plain_result("你还没有绑定账号。")
                return
            await session.delete(user)
            await session.commit()
            yield event.plain_result("已解绑。")

    @sk.command("sync")
    async def cmd_sync(self, event: AstrMessageEvent):
        """手动同步角色  用法: /sk sync"""
        sender_id = event.get_sender_id()
        async with await get_session() as session:
            user = await get_user_by_platform(session, sender_id)
            if not user:
                yield event.plain_result("未绑定森空岛账号。")
                return
            cred = CRED(cred=user.cred, token=user.cred_token)
            try:
                await self._sync_binding_chars(session, user, cred)
                await session.commit()
                ark_chars = await get_ark_characters(session, user)
                ef_chars = await get_ef_characters(session, user)
                parts = ["✅ 角色列表同步成功！"]
                if ark_chars:
                    parts.append(f"明日方舟: {len(ark_chars)}个")
                if ef_chars:
                    parts.append(f"终末地: {len(ef_chars)}个")
                if not ark_chars and not ef_chars:
                    parts.append("未找到任何角色")
                yield event.plain_result("\n".join(parts))
            except Exception as e:
                yield event.plain_result(f"同步失败：{e}")

    async def _sync_binding_chars(self, session, user: SkUser, cred_data: CRED):
        binding_list = await SklandAPI.get_binding(cred_data)
        for app in binding_list:
            for char in app.bindingList:
                if char.roles:
                    for role in char.roles:
                        await session.merge(
                            Character(
                                id=user.id,
                                uid=char.uid,
                                role_id=role.roleId,
                                nickname=role.nickname,
                                app_code=app.appCode,
                                channel_master_id=role.serverId,
                                isdefault=len(char.roles) == 1 or role.isDefault,
                            )
                        )
                else:
                    await session.merge(
                        Character(
                            id=user.id,
                            uid=char.uid,
                            nickname=char.nickName,
                            app_code=app.appCode,
                            channel_master_id=char.channelMasterId,
                            isdefault=len(app.bindingList) == 1 or char.isDefault,
                        )
                    )

    # ==================== 签到 ====================

    @sk.command("arksign")
    async def cmd_arksign(self, event: AstrMessageEvent):
        """明日方舟签到  用法: /sk arksign"""
        sender_id = event.get_sender_id()
        async with await get_session() as session:
            user = await get_user_by_platform(session, sender_id)
            if not user:
                yield event.plain_result("未绑定森空岛账号。")
                return
            chars = await get_ark_characters(session, user)
            if not chars:
                yield event.plain_result("未找到绑定的明日方舟角色。")
                return

            results = []
            for char in chars:
                cred = CRED(cred=user.cred, token=user.cred_token)
                try:
                    result = await call_api_with_refresh(
                        user, SklandAPI.ark_sign, cred, str(char.uid), char.channel_master_id
                    )
                    awards_text = "\n".join(
                        f"  {award.resource.name} x {award.count}" for award in result.awards
                    )
                    results.append(f"✅ {char.nickname} 签到成功，获得了:\n📦{awards_text}")
                except Exception as e:
                    error_msg = self._format_error(e)
                    if "请勿重复签到" in error_msg or "已签到" in error_msg:
                        results.append(f"ℹ️ {char.nickname} 已签到")
                    else:
                        results.append(f"❌ {char.nickname} 签到失败: {error_msg}")
                await session.commit()
            yield event.plain_result("\n\n".join(results))

    @sk.command("efsign")
    async def cmd_efsign(self, event: AstrMessageEvent):
        """终末地签到  用法: /sk efsign"""
        sender_id = event.get_sender_id()
        async with await get_session() as session:
            user = await get_user_by_platform(session, sender_id)
            if not user:
                yield event.plain_result("未绑定森空岛账号。")
                return
            chars = await get_ef_characters(session, user)
            if not chars:
                yield event.plain_result("未找到绑定的终末地角色。")
                return

            results = []
            for char in chars:
                cred = CRED(cred=user.cred, token=user.cred_token)
                try:
                    result = await call_api_with_refresh(
                        user, SklandAPI.endfield_sign, cred, char.role_id, char.channel_master_id
                    )
                    resource_info_map = result.resourceInfoMap or {}
                    award_ids = result.awardIds or []
                    award_lines = []
                    for award in award_ids:
                        info = resource_info_map.get(award.id)
                        if info:
                            name = info.name
                            count = info.count
                        else:
                            name = "未知物品"
                            count = 0
                        award_lines.append(f"  {name} x{count}")
                    awards_text = "\n".join(award_lines) if award_lines else "  (无奖励信息)"
                    results.append(f"✅ {char.nickname} 签到成功，获得了:\n📦{awards_text}")
                except Exception as e:
                    error_msg = self._format_error(e)
                    if "请勿重复签到" in error_msg or "已签到" in error_msg:
                        results.append(f"ℹ️ {char.nickname} 已签到")
                    else:
                        results.append(f"❌ {char.nickname} 签到失败: {error_msg}")
                await session.commit()
            yield event.plain_result("\n\n".join(results))

    # ==================== 纯文本看板 ====================

    @sk.command("arkmr")
    async def cmd_arkmr(self, event: AstrMessageEvent):
        """明日方舟看板  用法: /sk arkmr"""
        sender_id = event.get_sender_id()
        async with await get_session() as session:
            user = await get_user_by_platform(session, sender_id)
            if not user:
                yield event.plain_result("未绑定森空岛账号。")
                return
            char = await get_default_ark_character(session, user)
            if not char:
                yield event.plain_result("未找到绑定的明日方舟角色。")
                return

            cred = CRED(cred=user.cred, token=user.cred_token)
            try:
                card_data = await call_api_with_refresh(
                    user, SklandAPI.ark_card, cred, str(char.uid)
                )
                await session.commit()
            except Exception as e:
                yield event.plain_result(self._format_error(e))
                return

            lines = self._format_arkmr(card_data)
            yield event.plain_result("\n".join(lines))

    def _format_arkmr(self, card) -> list[str]:
        """格式化明日方舟看板"""
        s = card.status
        ap = s.ap
        now_ts = datetime.now().timestamp()

        # 理智
        ap_now = ap.ap_now
        if ap_now >= ap.max:
            ap_str = f"{ap_now} / {ap.max}  (已满)"
        else:
            recover_secs = max(0, ap.completeRecoveryTime - now_ts)
            ap_str = f"{ap_now} / {ap.max}  ({self._fmt_time(recover_secs)}后全满)"

        # 公招
        finished = card.recruit_finished
        total_r = len(card.recruit)
        recruit_str = f"{finished} / {total_r} 完成"
        if card.recruit and finished < total_r:
            recruit_str += f"  ({card.recruit_complete_time})"

        # 剿灭
        c = card.campaign
        if c.reward.total > 0:
            jm_str = f"已领取 {c.reward.current} / {c.reward.total}"
        else:
            jm_str = "无记录"

        # 每日/每周
        daily = card.routine.daily
        weekly = card.routine.weekly

        # 训练室
        training = getattr(card.building, "training", None) if card.building else None
        if training and training.trainee:
            char_info = card.charInfoMap.get(training.trainee.charId)
            trainee_name = char_info.name if char_info else "未知"
            skill_name = training.training_state
            remain = max(0, training.remainSecs)
            train_str = f"{trainee_name}  {skill_name}  (剩余 {self._fmt_time(remain)})"
        else:
            train_str = "空闲中"

        lines = [
            f"═ {s.name} ════════════════════════",
            f"  理智:    {ap_str}",
            f"  公招:    {recruit_str}",
            f"  剿灭:    {jm_str}",
            f"  每日:    {daily.current} / {daily.total}",
            f"  每周:    {weekly.current} / {weekly.total}",
            f"  训练室:  {train_str}",
            "═════════════════════════════════════",
        ]
        return lines

    @sk.command("efmr")
    async def cmd_efmr(self, event: AstrMessageEvent):
        """终末地看板  用法: /sk efmr"""
        sender_id = event.get_sender_id()
        async with await get_session() as session:
            user = await get_user_by_platform(session, sender_id)
            if not user:
                yield event.plain_result("未绑定森空岛账号。")
                return
            char = await get_default_ef_character(session, user)
            if not char:
                yield event.plain_result("未找到绑定的终末地角色。")
                return

            cred = CRED(cred=user.cred, token=user.cred_token)
            try:
                skland_uid = user.user_id or sender_id
                card_data = await call_api_with_refresh(
                    user, SklandAPI.endfield_card, cred, skland_uid, char
                )
                await session.commit()
            except Exception as e:
                yield event.plain_result(self._format_error(e))
                return

            lines = self._format_efmr(card_data)
            yield event.plain_result("\n".join(lines))

    def _format_efmr(self, card) -> list[str]:
        """格式化终末地看板"""
        base = card.base
        dungeon = card.dungeon
        dm = card.dailyMission
        wm = card.weeklyMission
        now_ts = datetime.now().timestamp()

        # 理智
        try:
            cur_ap = int(dungeon.curStamina) if dungeon.curStamina else 0
            max_ap = int(dungeon.maxStamina) if dungeon.maxStamina else 1
            max_ts = float(dungeon.maxTs) if dungeon.maxTs else now_ts
            remain_secs = max(0, max_ts - now_ts)
            if remain_secs <= 0:
                ap_str = f"{cur_ap} / {max_ap}  (已满)"
            else:
                ap_str = f"{cur_ap} / {max_ap}  ({self._fmt_time(remain_secs)}后全满)"
        except Exception:
            ap_str = "未知"

        # 每日/每周
        daily_str = f"活跃度 {dm.dailyActivation} / {dm.maxDailyActivation}"
        weekly_str = f"每周事务 {wm.score} / {wm.total}"

        # 据点票券
        domain_lines = []
        for domain in card.domain:
            name = domain.name or "未知据点"
            mgr = domain.moneyMgr
            if mgr:
                try:
                    total = int(mgr.total) if mgr.total else 0
                    count = int(mgr.count) if mgr.count else 0
                    domain_lines.append(f"  {name}:  {count} / {total}")
                except Exception:
                    domain_lines.append(f"  {name}:  数据异常")

        lines = [
            f"═ {base.name} ════════════════════════",
            f"  理智:      {ap_str}",
            f"  每日任务:  {daily_str}",
            f"  每周任务:  {weekly_str}",
        ]
        if domain_lines:
            lines.append("  据点票券:")
            lines.extend(domain_lines)
        lines.append("═════════════════════════════════════")
        return lines

    @sk.command("mr")
    async def cmd_mr(self, event: AstrMessageEvent):
        """综合看板(管理员)  用法: /sk mr"""
        sender_id = event.get_sender_id()
        async with await get_session() as session:
            user = await get_user_by_platform(session, sender_id)
            if not user:
                yield event.plain_result("未绑定森空岛账号。")
                return

            final_lines = ["═ 森空岛综合看板 ════════════════════════", ""]

            # 方舟
            ark_char = await get_default_ark_character(session, user)
            if ark_char:
                cred = CRED(cred=user.cred, token=user.cred_token)
                try:
                    ark_card = await call_api_with_refresh(
                        user, SklandAPI.ark_card, cred, str(ark_char.uid)
                    )
                    final_lines.append("【明日方舟】")
                    final_lines.extend(self._format_arkmr(ark_card))
                    final_lines.append("")
                except Exception as e:
                    final_lines.append(f"【明日方舟】{self._format_error(e)}")
                    final_lines.append("")
                await session.commit()
            else:
                final_lines.append("【明日方舟】未绑定角色")
                final_lines.append("")

            # 终末地
            ef_char = await get_default_ef_character(session, user)
            if ef_char:
                cred = CRED(cred=user.cred, token=user.cred_token)
                try:
                    skland_uid = user.user_id or sender_id
                    ef_card = await call_api_with_refresh(
                        user, SklandAPI.endfield_card, cred, skland_uid, ef_char
                    )
                    final_lines.append("【终末地】")
                    final_lines.extend(self._format_efmr(ef_card))
                    final_lines.append("")
                except Exception as e:
                    final_lines.append(f"【终末地】{self._format_error(e)}")
                    final_lines.append("")
                await session.commit()
            else:
                final_lines.append("【终末地】未绑定角色")
                final_lines.append("")

            final_lines.append("═════════════════════════════════════")
            yield event.plain_result("\n".join(final_lines))

    # ==================== 工具方法 ====================

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        """格式化秒数为  xh xmin"""
        if seconds <= 0:
            return "0min"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        if hours > 0:
            return f"{hours}h {minutes}min"
        return f"{minutes}min"
