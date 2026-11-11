"""
Nexus League Bot v5
Python 3.10+ / discord.py 2.x
SQLite stores operational data only. Player registration details (including Riot ID)
are sent to Discord and are NEVER written to SQLite.
"""
from __future__ import annotations

import os
import sqlite3
import logging
import asyncio
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from aiohttp import web

# ---------------- Configuration ----------------
TOKEN = os.getenv("DISCORD_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "nexus_league_v5.sqlite3")
GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None
REPORT_USER_ID = 1392895521433321502
REGISTRATION_CHANNEL_ID = 1566055273146093599
RECRUIT_CHANNELS = {
    "normal": 1569643108147265709,
    "duo": 1569643437035229326,
    "flex": 1569643504994285,
}
CUSTOM_CHANNEL_ID = 1567318455391101030
ROLE_NAMES = ("ノーマル", "ランク", "カスタム", "大会")
TEAM_CATEGORY_ID = int(os.getenv("TEAM_CATEGORY_ID", "0")) or None
MATCHING_CATEGORY_ID = int(os.getenv("MATCHING_CATEGORY_ID", "0")) or None
OPERATIONS_ROLE_ID = int(os.getenv("OPERATIONS_ROLE_ID", "0")) or None
JST = ZoneInfo("Asia/Tokyo")
PORT = int(os.getenv("PORT", "10000"))
LOG = logging.getLogger("nexus")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

RANKS = [
    ("CHALLENGER", "Challenger"), ("GRANDMASTER", "Grandmaster"),
    ("MASTER", "Master"), ("DIAMOND_1_2", "Diamond I-II"),
    ("DIAMOND_3_4", "Diamond III-IV"), ("EMERALD_1_2", "Emerald I-II"),
    ("EMERALD_3_4", "Emerald III-IV"), ("PLATINUM", "Platinum"),
    ("COACH", "コーチ"),
]
LANES = ("TOP", "JGL", "MID", "ADC", "SUP", "コーチ")
RECRUIT_KIND_LABELS = {
    "normal": "ノーマル・ARAM", "duo": "デュオランク",
    "flex": "フレックス", "custom": "カスタム",
}
ROLE_MENTION_NAMES = {"normal": "ノーマル", "duo": "ランク", "flex": "ランク", "custom": "カスタム"}

# ---------------- Database ----------------
def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con

def init_db() -> None:
    with connect() as con:
        # Explicitly purge legacy registration data before creating the v5 schema.
        con.execute("DROP TABLE IF EXISTS players")
        con.execute("""
        CREATE TABLE IF NOT EXISTS recruitment_posts(
            message_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL, thread_id INTEGER NOT NULL,
            kind TEXT NOT NULL, created_at TEXT NOT NULL
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS recruitment_participants(
            message_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('regular','late')),
            joined_at TEXT NOT NULL,
            PRIMARY KEY(message_id,user_id),
            FOREIGN KEY(message_id) REFERENCES recruitment_posts(message_id) ON DELETE CASCADE
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS vc_sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL, channel_id INTEGER NOT NULL,
            joined_at TEXT NOT NULL, left_at TEXT
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS vc_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL, channel_id INTEGER NOT NULL,
            event TEXT NOT NULL, occurred_at TEXT NOT NULL
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS tournaments(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
            creator_id INTEGER NOT NULL, name TEXT NOT NULL, starts_at TEXT NOT NULL,
            rules TEXT NOT NULL, entry_type TEXT NOT NULL, status TEXT NOT NULL,
            channel_id INTEGER, message_id INTEGER, created_at TEXT NOT NULL
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS tournament_entries(
            id INTEGER PRIMARY KEY AUTOINCREMENT, tournament_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL, team_name TEXT NOT NULL, members TEXT NOT NULL,
            created_at TEXT NOT NULL, UNIQUE(tournament_id,user_id),
            FOREIGN KEY(tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS operation_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER,
            actor_id INTEGER, action TEXT NOT NULL, detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_vc_user_time ON vc_sessions(user_id,joined_at,left_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_recruit_created ON recruitment_posts(created_at)")

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def log_action(guild_id: Optional[int], actor_id: Optional[int], action: str, detail: str = "") -> None:
    with connect() as con:
        con.execute("INSERT INTO operation_logs(guild_id,actor_id,action,detail,created_at) VALUES(?,?,?,?,?)",
                    (guild_id, actor_id, action, detail[:1500], now_iso()))

def is_admin():
    return app_commands.checks.has_permissions(administrator=True)

async def safe_ephemeral(interaction: discord.Interaction, content: str):
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=True)
    else:
        await interaction.response.send_message(content, ephemeral=True)

# ---------------- Common UI: recruitment ----------------
class RecruitmentView(discord.ui.View):
    """Persistent per-message buttons; message_id is resolved from interaction.message."""
    def __init__(self):
        super().__init__(timeout=None)

    async def _change(self, interaction: discord.Interaction, status: str):
        if not interaction.message or not interaction.guild:
            return await safe_ephemeral(interaction, "サーバー内の募集投稿から操作してください。")
        mid, uid = interaction.message.id, interaction.user.id
        with connect() as con:
            post = con.execute("SELECT thread_id FROM recruitment_posts WHERE message_id=?", (mid,)).fetchone()
            if not post:
                return await safe_ephemeral(interaction, "募集データが見つかりません。")
            existing = con.execute("SELECT status FROM recruitment_participants WHERE message_id=? AND user_id=?",
                                   (mid, uid)).fetchone()
            if status == "withdraw":
                con.execute("DELETE FROM recruitment_participants WHERE message_id=? AND user_id=?", (mid, uid))
            else:
                con.execute("""INSERT INTO recruitment_participants(message_id,user_id,status,joined_at)
                               VALUES(?,?,?,?) ON CONFLICT(message_id,user_id)
                               DO UPDATE SET status=excluded.status, joined_at=excluded.joined_at""",
                            (mid, uid, status, now_iso()))
        thread = interaction.guild.get_thread(post["thread_id"])
        if thread is None:
            try:
                fetched = await interaction.guild.fetch_channel(post["thread_id"])
                thread = fetched if isinstance(fetched, discord.Thread) else None
            except discord.HTTPException:
                thread = None
        if thread is not None:
            try:
                if status == "withdraw":
                    await thread.remove_user(interaction.user)
                    await thread.send(f"🚪 {interaction.user.mention} さんが辞退しました。")
                else:
                    await thread.add_user(interaction.user)
                    label = "途中参加" if status == "late" else "通常参加"
                    await thread.send(f"🙋 {interaction.user.mention} さんが{label}しました。")
            except discord.HTTPException:
                LOG.exception("Thread membership update failed")
        await self._refresh(interaction.message)
        if status == "withdraw":
            await safe_ephemeral(interaction, "辞退しました。再参加できます。")
        else:
            await safe_ephemeral(interaction, f"{'途中参加' if status == 'late' else '参加'}を受け付けました。")

    async def _refresh(self, message: discord.Message):
        with connect() as con:
            rows = con.execute("""SELECT user_id,status FROM recruitment_participants
                                  WHERE message_id=? ORDER BY joined_at""", (message.id,)).fetchall()
        regular = [f"<@{r['user_id']}>" for r in rows if r["status"] == "regular"]
        late = [f"<@{r['user_id']}>" for r in rows if r["status"] == "late"]
        embed = message.embeds[0] if message.embeds else discord.Embed(title="募集")
        # Preserve title/description and append participant fields.
        embed.clear_fields()
        embed.add_field(name=f"通常参加 ({len(regular)})", value="\n".join(regular) or "なし", inline=True)
        embed.add_field(name=f"途中参加 ({len(late)})", value="\n".join(late) or "なし", inline=True)
        try:
            await message.edit(embed=embed, view=self)
        except discord.HTTPException:
            LOG.exception("Could not refresh recruitment message")

    @discord.ui.button(label="参加", style=discord.ButtonStyle.success, emoji="🙋", custom_id="nexus:v5:recruit:join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._change(interaction, "regular")

    @discord.ui.button(label="途中参加", style=discord.ButtonStyle.primary, emoji="⏩", custom_id="nexus:v5:recruit:late")
    async def late(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._change(interaction, "late")

    @discord.ui.button(label="辞退", style=discord.ButtonStyle.danger, emoji="🚪", custom_id="nexus:v5:recruit:withdraw")
    async def withdraw(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._change(interaction, "withdraw")

async def create_recruit_thread(message: discord.Message, kind: str):
    label = RECRUIT_KIND_LABELS[kind]
    role = discord.utils.get(message.guild.roles, name=ROLE_MENTION_NAMES[kind]) if message.guild else None
    mention = role.mention if role else ""
    thread = await message.create_thread(name=f"{label}｜{message.author.display_name}"[:100],
                                         auto_archive_duration=1440)
    await thread.send(f"{mention} {message.author.mention} さんの募集スレッドです。",
                      allowed_mentions=discord.AllowedMentions(roles=[role] if role else [], users=True))
    with connect() as con:
        con.execute("""INSERT OR REPLACE INTO recruitment_posts
            (message_id,guild_id,channel_id,thread_id,kind,created_at) VALUES(?,?,?,?,?,?)""",
            (message.id, message.guild.id, message.channel.id, thread.id, kind, now_iso()))
    return thread

# ---------------- Registration: intentionally no persistence ----------------
class RegistrationModal(discord.ui.Modal, title="プレイヤー登録情報"):
    riot_id = discord.ui.TextInput(label="Riot ID（名前#タグ）", max_length=100)
    role = discord.ui.TextInput(label="メインロール（TOP/JGL/MID/ADC/SUP/コーチ）", max_length=20)
    intro = discord.ui.TextInput(label="自己PR・得意チャンピオン", style=discord.TextStyle.paragraph,
                                 required=False, max_length=900)
    def __init__(self, rank: str):
        super().__init__()
        self.rank = rank

    async def on_submit(self, interaction: discord.Interaction):
        riot = self.riot_id.value.strip()
        role = self.role.value.strip().upper()
        if "#" not in riot or not all(riot.split("#", 1)) or role not in LANES:
            return await safe_ephemeral(interaction, "Riot IDは名前#タグ、ロールはTOP/JGL/MID/ADC/SUP/コーチで入力してください。")
        channel = interaction.guild.get_channel(REGISTRATION_CHANNEL_ID) if interaction.guild else None
        if channel is None and interaction.guild:
            try:
                channel = await interaction.guild.fetch_channel(REGISTRATION_CHANNEL_ID)
            except discord.HTTPException:
                channel = None
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await safe_ephemeral(interaction, "登録情報送信先チャンネルが見つかりません。登録は完了していません。")
        rank_label = dict(RANKS).get(self.rank, self.rank)
        embed = discord.Embed(title="プレイヤー登録申請", color=discord.Color.blurple(),
                              timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Discord", value=f"{interaction.user.mention}（{interaction.user.id}）", inline=False)
        embed.add_field(name="Riot ID", value=discord.utils.escape_markdown(riot), inline=True)
        embed.add_field(name="最高ランク", value=rank_label, inline=True)
        embed.add_field(name="メインロール", value=role, inline=True)
        embed.add_field(name="自己PR", value=self.intro.value.strip() or "未記入", inline=False)
        embed.set_footer(text="Google Sheets等への登録は運営が手動で行ってください")
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            LOG.exception("Registration submission failed")
            return await safe_ephemeral(interaction, "登録情報の送信に失敗しました。登録は完了していません。運営に連絡してください。")
        await safe_ephemeral(interaction, "登録情報を運営チャンネルへ送信しました。運営による確認・手動登録をお待ちください。")

class RankSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="最高ランクを選択", min_values=1, max_values=1,
                         options=[discord.SelectOption(label=label, value=key) for key, label in RANKS])
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RegistrationModal(self.values[0]))

class RankSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(RankSelect())

class RegistrationPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="プレイヤー登録", style=discord.ButtonStyle.success,
                       custom_id="nexus:v5:registration:open")
    async def open(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("最高ランクを選択してください。", view=RankSelectView(), ephemeral=True)

# ---------------- FA card: post only, no database ----------------
class FaModal(discord.ui.Modal, title="FA選手カード"):
    riot = discord.ui.TextInput(label="Riot ID（名前#タグ）", max_length=100)
    rank = discord.ui.TextInput(label="ランク", max_length=60)
    role = discord.ui.TextInput(label="メインロール", max_length=20)
    intro = discord.ui.TextInput(label="自己PR", style=discord.TextStyle.paragraph, required=False, max_length=900)
    async def on_submit(self, interaction: discord.Interaction):
        riot = self.riot.value.strip()
        if "#" not in riot:
            return await safe_ephemeral(interaction, "Riot IDは名前#タグ形式で入力してください。")
        embed = discord.Embed(title="FA選手カード", color=discord.Color.blurple())
        embed.set_author(name=f"{riot}｜{self.rank.value}｜{self.role.value}",
                         icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="Riot ID", value=discord.utils.escape_markdown(riot), inline=True)
        embed.add_field(name="ランク", value=self.rank.value, inline=True)
        embed.add_field(name="ロール", value=self.role.value, inline=True)
        embed.add_field(name="自己PR", value=self.intro.value.strip() or "未記入", inline=False)
        embed.set_footer(text=f"投稿者: {interaction.user}")
        try:
            await interaction.channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            return await safe_ephemeral(interaction, "FAカードを投稿できませんでした。")
        await safe_ephemeral(interaction, "FAカードを投稿しました。")

class FaPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="FA選手カードを作成", style=discord.ButtonStyle.primary,
                       custom_id="nexus:v5:fa:create")
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FaModal())

# ---------------- Role panel ----------------
class RolePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for name in ROLE_NAMES:
            b = discord.ui.Button(label=f"＠{name}", style=discord.ButtonStyle.primary,
                                  custom_id=f"nexus:v5:role:add:{name}")
            async def callback(interaction: discord.Interaction, role_name=name):
                await self.toggle(interaction, role_name)
            b.callback = callback
            self.add_item(b)
        clear = discord.ui.Button(label="全てのロールを外す", style=discord.ButtonStyle.danger,
                                  custom_id="nexus:v5:role:clear", row=1)
        clear.callback = self.clear
        self.add_item(clear)

    async def toggle(self, interaction: discord.Interaction, name: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await safe_ephemeral(interaction, "サーバー内で操作してください。")
        role = discord.utils.get(interaction.guild.roles, name=name)
        if role is None:
            return await safe_ephemeral(interaction, f"ロール「{name}」が見つかりません。")
        me = interaction.guild.me
        if me is None or role >= me.top_role or role.managed:
            return await safe_ephemeral(interaction, f"ロール「{name}」はBotの権限階層上、操作できません。")
        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason="Nexus role panel")
                msg = f"＠{name} を解除しました。"
            else:
                await interaction.user.add_roles(role, reason="Nexus role panel")
                msg = f"＠{name} を付与しました。"
            await safe_ephemeral(interaction, msg)
        except discord.HTTPException:
            await safe_ephemeral(interaction, "ロールを変更できませんでした。権限とロール階層を確認してください。")

    async def clear(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await safe_ephemeral(interaction, "サーバー内で操作してください。")
        roles = [r for r in interaction.guild.roles if r.name in ROLE_NAMES and r in interaction.user.roles]
        me = interaction.guild.me
        removable = [r for r in roles if me and not r.managed and r < me.top_role]
        try:
            if removable:
                await interaction.user.remove_roles(*removable, reason="Nexus role panel clear")
            blocked = len(roles) - len(removable)
            await safe_ephemeral(interaction, f"対象ロールを解除しました。"+(f" {blocked}個は権限階層上解除できませんでした。" if blocked else ""))
        except discord.HTTPException:
            await safe_ephemeral(interaction, "ロール解除に失敗しました。")

# ---------------- Team & matching private intake ----------------
class PrivateRequestModal(discord.ui.Modal):
    subject = discord.ui.TextInput(label="チーム名／希望内容", max_length=100)
    details = discord.ui.TextInput(label="申請内容", style=discord.TextStyle.paragraph, max_length=1500)
    def __init__(self, request_type: str):
        super().__init__(title="チーム申請" if request_type == "team" else "マッチング希望")
        self.request_type = request_type
    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await safe_ephemeral(interaction, "サーバー内で実行してください。")
        await interaction.response.defer(ephemeral=True, thinking=True)
        category_id = TEAM_CATEGORY_ID if self.request_type == "team" else MATCHING_CATEGORY_ID
        category = interaction.guild.get_channel(category_id) if category_id else None
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if interaction.guild.me:
            overwrites[interaction.guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        if OPERATIONS_ROLE_ID:
            ops = interaction.guild.get_role(OPERATIONS_ROLE_ID)
            if ops:
                overwrites[ops] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        safe_name = f"{'team' if self.request_type == 'team' else 'matching'}-{interaction.user.id}"
        try:
            channel = await interaction.guild.create_text_channel(
                name=safe_name[:90], category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites, topic=f"{self.subject.value} | applicant={interaction.user.id}")
            embed = discord.Embed(title="チーム結成・解散申請" if self.request_type == "team" else "マッチング受付",
                                  description=self.details.value, color=discord.Color.blurple())
            embed.add_field(name="申請者", value=interaction.user.mention)
            embed.add_field(name="件名", value=self.subject.value)
            embed.set_footer(text="マッチングの実作業は別AIが担当します。" if self.request_type == "matching" else "運営確認用")
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            log_action(interaction.guild.id, interaction.user.id, f"{self.request_type}_request", channel.name)
            await interaction.followup.send(f"非公開受付チャンネルを作成しました: {channel.mention}", ephemeral=True)
        except discord.HTTPException:
            LOG.exception("Private request channel creation failed")
            await interaction.followup.send("受付チャンネルを作成できませんでした。Bot権限を確認してください。", ephemeral=True)

class RequestPanelView(discord.ui.View):
    def __init__(self, panel_type: str):
        super().__init__(timeout=None)
        self.panel_type = panel_type
    @discord.ui.button(label="結成を申請", style=discord.ButtonStyle.success, custom_id="nexus:v5:team:create")
    async def team_create(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.panel_type != "team":
            return await safe_ephemeral(interaction, "このパネルでは使用できません。")
        await interaction.response.send_modal(PrivateRequestModal("team"))
    @discord.ui.button(label="解散を申請", style=discord.ButtonStyle.danger, custom_id="nexus:v5:team:disband")
    async def team_disband(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.panel_type != "team":
            return await safe_ephemeral(interaction, "このパネルでは使用できません。")
        await interaction.response.send_modal(PrivateRequestModal("team"))
    @discord.ui.button(label="マッチングを希望する", style=discord.ButtonStyle.primary, custom_id="nexus:v5:matching:request")
    async def matching(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.panel_type != "matching":
            return await safe_ephemeral(interaction, "このパネルでは使用できません。")
        await interaction.response.send_modal(PrivateRequestModal("matching"))

# ---------------- Tournament ----------------
class TournamentEntryModal(discord.ui.Modal, title="大会チームエントリー"):
    team = discord.ui.TextInput(label="チーム名", max_length=80)
    members = discord.ui.TextInput(label="メンバー（名前やDiscord IDを記載）",
                                   style=discord.TextStyle.paragraph, max_length=800)
    def __init__(self, tournament_id: int):
        super().__init__()
        self.tournament_id = tournament_id
    async def on_submit(self, interaction: discord.Interaction):
        with connect() as con:
            t = con.execute("SELECT status FROM tournaments WHERE id=?", (self.tournament_id,)).fetchone()
            if not t or t["status"] != "open":
                return await safe_ephemeral(interaction, "この大会は受付中ではありません。")
            try:
                con.execute("""INSERT INTO tournament_entries(tournament_id,user_id,team_name,members,created_at)
                               VALUES(?,?,?,?,?)""",
                            (self.tournament_id, interaction.user.id, self.team.value.strip(),
                             self.members.value.strip(), now_iso()))
            except sqlite3.IntegrityError:
                return await safe_ephemeral(interaction, "この大会には既にエントリー済みです。")
        await safe_ephemeral(interaction, "大会エントリーを受け付けました。")

class TournamentPanelView(discord.ui.View):
    def __init__(self, tournament_id: int):
        super().__init__(timeout=None)
        self.tournament_id = tournament_id
        b = discord.ui.Button(label="チームエントリー", style=discord.ButtonStyle.success,
                              custom_id=f"nexus:v5:tournament:entry:{tournament_id}")
        b.callback = self.entry
        self.add_item(b)
        b2 = discord.ui.Button(label="参加一覧", style=discord.ButtonStyle.secondary,
                               custom_id=f"nexus:v5:tournament:list:{tournament_id}")
        b2.callback = self.list_entries
        self.add_item(b2)
    async def entry(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TournamentEntryModal(self.tournament_id))
    async def list_entries(self, interaction: discord.Interaction):
        with connect() as con:
            rows = con.execute("SELECT team_name,user_id FROM tournament_entries WHERE tournament_id=? ORDER BY id",
                               (self.tournament_id,)).fetchall()
        desc = "\n".join(f"**{r['team_name']}** — <@{r['user_id']}>" for r in rows) or "まだエントリーはありません。"
        await safe_ephemeral(interaction, desc[:1900])

class TournamentCreateModal(discord.ui.Modal, title="大会作成"):
    name = discord.ui.TextInput(label="大会名", max_length=100)
    starts = discord.ui.TextInput(label="開催日時（JST。例 2026-12-01 20:00）", max_length=30)
    rules = discord.ui.TextInput(label="ルール", style=discord.TextStyle.paragraph, max_length=1500)
    entry_type = discord.ui.TextInput(label="参加方式（チーム／個人）", max_length=20)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            dt = datetime.strptime(self.starts.value.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=JST)
        except ValueError:
            return await safe_ephemeral(interaction, "日時形式が正しくありません。YYYY-MM-DD HH:MM で入力してください。")
        if self.entry_type.value.strip() not in ("チーム", "個人"):
            return await safe_ephemeral(interaction, "参加方式は「チーム」または「個人」です。")
        with connect() as con:
            cur = con.execute("""INSERT INTO tournaments(guild_id,creator_id,name,starts_at,rules,entry_type,status,created_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (interaction.guild_id, interaction.user.id, self.name.value.strip(), dt.isoformat(),
                 self.rules.value.strip(), self.entry_type.value.strip(), "open", now_iso()))
            tid = cur.lastrowid
        embed = discord.Embed(title=f"🏆 {self.name.value}", description=self.rules.value,
                              color=discord.Color.gold())
        embed.add_field(name="開催日時", value=dt.strftime("%Y-%m-%d %H:%M JST"))
        embed.add_field(name="参加方式", value=self.entry_type.value)
        try:
            msg = await interaction.channel.send(embed=embed, view=TournamentPanelView(tid))
            with connect() as con:
                con.execute("UPDATE tournaments SET channel_id=?,message_id=? WHERE id=?",
                            (msg.channel.id, msg.id, tid))
            await safe_ephemeral(interaction, f"大会を作成しました（ID: {tid}）。")
        except discord.HTTPException:
            with connect() as con:
                con.execute("UPDATE tournaments SET status='draft' WHERE id=?", (tid,))
            await safe_ephemeral(interaction, "大会情報は保存しましたが、受付パネルの投稿に失敗しました。運営が再設置してください。")

# ---------------- Bot ----------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.message_content = True

class NexusBot(commands.Bot):
    async def setup_hook(self):
        self.add_view(RegistrationPanelView())
        self.add_view(FaPanelView())
        self.add_view(RolePanelView())
        self.add_view(RecruitmentView())
        self.add_view(RequestPanelView("team"))
        self.add_view(RequestPanelView("matching"))
        # Tournament views have per-tournament custom IDs and are rehydrated below.
        with connect() as con:
            ids = [r["id"] for r in con.execute("SELECT id FROM tournaments WHERE status='open'").fetchall()]
        for tid in ids:
            self.add_view(TournamentPanelView(tid))
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        if not self.daily_dm.is_running():
            self.daily_dm.start()

    async def on_ready(self):
        LOG.info("Ready as %s (%s)", self.user, self.user.id if self.user else "?")

    @tasks.loop(time=time(hour=8, minute=0, tzinfo=JST))
    async def daily_dm(self):
        yesterday = (datetime.now(JST).date() - timedelta(days=1))
        start = datetime.combine(yesterday, time.min, tzinfo=JST)
        end = start + timedelta(days=1)
        report = build_daily_report(start, end)
        user = self.get_user(REPORT_USER_ID)
        if user is None:
            try:
                user = await self.fetch_user(REPORT_USER_ID)
            except discord.HTTPException:
                LOG.exception("Report recipient fetch failed")
                return
        try:
            await user.send(report)
        except discord.HTTPException:
            LOG.exception("Daily report DM failed")

bot = NexusBot(command_prefix="!", intents=intents)

@bot.event
async def on_message(message: discord.Message):
    if not message.author.bot and message.guild:
        kind = next((k for k, cid in RECRUIT_CHANNELS.items() if cid == message.channel.id), None)
        if kind:
            try:
                thread = await create_recruit_thread(message, kind)
                role_name = ROLE_MENTION_NAMES[kind]
                role = discord.utils.get(message.guild.roles, name=role_name)
                mention = role.mention if role else ""
                embed = discord.Embed(title=f"募集：{RECRUIT_KIND_LABELS[kind]}",
                                      description=message.content[:3500] or "募集内容なし",
                                      color=discord.Color.green())
                embed.add_field(name="募集主", value=message.author.mention)
                embed.add_field(name="通常参加", value="なし", inline=True)
                embed.add_field(name="途中参加", value="なし", inline=True)
                panel = await message.reply(content=f"{mention} 募集スレッド: {thread.mention}",
                    embed=embed, view=RecruitmentView(), mention_author=False,
                    allowed_mentions=discord.AllowedMentions(roles=[role] if role else [], users=True))
                with connect() as con:
                    con.execute("UPDATE recruitment_posts SET message_id=? WHERE thread_id=?", (panel.id, thread.id))
            except discord.HTTPException:
                LOG.exception("Auto recruitment failed for message %s", message.id)
                try:
                    await message.reply("募集スレッドの作成に失敗しました。Bot権限を確認してください。", mention_author=False)
                except discord.HTTPException:
                    pass
    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if before.channel == after.channel:
        return
    ts = now_iso()
    with connect() as con:
        if before.channel:
            row = con.execute("""SELECT id,joined_at FROM vc_sessions WHERE guild_id=? AND user_id=?
                AND channel_id=? AND left_at IS NULL ORDER BY id DESC LIMIT 1""",
                (member.guild.id, member.id, before.channel.id)).fetchone()
            if row:
                con.execute("UPDATE vc_sessions SET left_at=? WHERE id=?", (ts, row["id"]))
            con.execute("INSERT INTO vc_events(guild_id,user_id,channel_id,event,occurred_at) VALUES(?,?,?,?,?)",
                        (member.guild.id, member.id, before.channel.id, "leave", ts))
        if after.channel:
            con.execute("INSERT INTO vc_sessions(guild_id,user_id,channel_id,joined_at) VALUES(?,?,?,?)",
                        (member.guild.id, member.id, after.channel.id, ts))
            con.execute("INSERT INTO vc_events(guild_id,user_id,channel_id,event,occurred_at) VALUES(?,?,?,?,?)",
                        (member.guild.id, member.id, after.channel.id, "join", ts))

# ---------------- Reporting helpers ----------------
def build_daily_report(start: datetime, end: datetime) -> str:
    a, b = start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()
    with connect() as con:
        joins = con.execute("""SELECT COUNT(*) n,COUNT(DISTINCT user_id) users FROM vc_events
            WHERE event='join' AND occurred_at>=? AND occurred_at<?""", (a,b)).fetchone()
        sessions = con.execute("""SELECT user_id,joined_at,left_at FROM vc_sessions
            WHERE joined_at<? AND (left_at IS NULL OR left_at>?)""", (b,a)).fetchall()
        recruit = con.execute("SELECT COUNT(*) n FROM recruitment_posts WHERE created_at>=? AND created_at<?",
                              (a,b)).fetchone()["n"]
        top = con.execute("""SELECT p.kind,COUNT(*) n FROM recruitment_posts p
            WHERE p.created_at>=? AND p.created_at<? GROUP BY p.kind ORDER BY n DESC LIMIT 3""", (a,b)).fetchall()
    seconds_by_user = {}
    for s in sessions:
        joined = max(datetime.fromisoformat(s["joined_at"]), start.astimezone(timezone.utc))
        left = min(datetime.fromisoformat(s["left_at"]) if s["left_at"] else end.astimezone(timezone.utc),
                   end.astimezone(timezone.utc))
        seconds_by_user[s["user_id"]] = seconds_by_user.get(s["user_id"], 0) + max(0, (left-joined).total_seconds())
    total_hours = sum(seconds_by_user.values()) / 3600
    top_text = "\n".join(f"{RECRUIT_KIND_LABELS.get(r['kind'],r['kind'])}: {r['n']}回" for r in top) or "なし"
    return (f"📊 **Nexus League 昨日の活動報告**（{start.strftime('%Y-%m-%d')} JST）\n"
            f"VC入室回数: **{joins['n']}回**（利用者 {joins['users']}人）\n"
            f"VC利用時間合計: **{total_hours:.1f}時間**\n"
            f"募集使用回数: **{recruit}回**\n募集使用TOP3:\n{top_text}\n"
            f"VC利用者数: **{len(seconds_by_user)}人**")

def report_for_period(days: int) -> str:
    end = datetime.now(JST)
    start = end - timedelta(days=days)
    a, b = start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()
    with connect() as con:
        ev = con.execute("SELECT COUNT(*) n FROM vc_events WHERE event='join' AND occurred_at>=? AND occurred_at<?",
                         (a,b)).fetchone()["n"]
        rec = con.execute("SELECT COUNT(*) n FROM recruitment_posts WHERE created_at>=? AND created_at<?",
                          (a,b)).fetchone()["n"]
        sessions = con.execute("SELECT joined_at,left_at FROM vc_sessions WHERE joined_at<? AND (left_at IS NULL OR left_at>?)",
                               (b,a)).fetchall()
    secs = 0
    for s in sessions:
        j = max(datetime.fromisoformat(s["joined_at"]), start.astimezone(timezone.utc))
        l = min(datetime.fromisoformat(s["left_at"]) if s["left_at"] else end.astimezone(timezone.utc),
                end.astimezone(timezone.utc))
        secs += max(0, (l-j).total_seconds())
    return f"過去{days}日: VC入室 {ev}回 / VC利用 {secs/3600:.1f}時間 / 募集 {rec}回"

# ---------------- Slash commands ----------------
@bot.tree.command(name="setup", description="プレイヤー登録パネルを設置")
@is_admin()
async def setup_cmd(interaction: discord.Interaction):
    await interaction.channel.send(embed=discord.Embed(title="Nexus League｜プレイヤー登録",
        description="ボタンからランクを選択し、登録情報を運営チャンネルへ送信してください。Botは登録情報を保存しません。"),
        view=RegistrationPanelView())
    log_action(interaction.guild_id, interaction.user.id, "setup")
    await safe_ephemeral(interaction, "登録パネルを設置しました。")

@bot.tree.command(name="fa_card", description="FA選手カード作成パネルを設置")
@is_admin()
async def fa_card_cmd(interaction: discord.Interaction):
    await interaction.channel.send(embed=discord.Embed(title="FA選手カード", description="ボタンからカードを投稿できます。"),
                                   view=FaPanelView())
    await safe_ephemeral(interaction, "FAカードパネルを設置しました。")

@bot.tree.command(name="recruit_panel", description="カスタム募集パネルを設置")
@is_admin()
async def recruit_panel_cmd(interaction: discord.Interaction):
    channel = interaction.guild.get_channel(CUSTOM_CHANNEL_ID) if interaction.guild else None
    if not isinstance(channel, discord.TextChannel):
        return await safe_ephemeral(interaction, f"カスタム募集チャンネルが見つかりません（{CUSTOM_CHANNEL_ID}）。")
    await channel.send(embed=discord.Embed(title="カスタム募集", description="このチャンネルで募集内容を投稿するとスレッドを作成します。"))
    await safe_ephemeral(interaction, "カスタム募集案内を設置しました。")

@bot.tree.command(name="team_panel", description="チーム申請パネルを設置")
@is_admin()
async def team_panel_cmd(interaction: discord.Interaction):
    view = RequestPanelView("team")
    await interaction.channel.send(embed=discord.Embed(title="チーム管理", description="結成・解散申請は非公開チャンネルで運営が確認します。"), view=view)
    await safe_ephemeral(interaction, "チームパネルを設置しました。")

@bot.tree.command(name="matching_panel", description="マッチング受付パネルを設置")
@is_admin()
async def matching_panel_cmd(interaction: discord.Interaction):
    await interaction.channel.send(embed=discord.Embed(title="マッチング受付", description="Botは希望受付のみ行います。実際のマッチングは別AIが担当します。"),
                                   view=RequestPanelView("matching"))
    await safe_ephemeral(interaction, "マッチングパネルを設置しました。")

@bot.tree.command(name="role_panel", description="4種類のロールパネルを設置")
@is_admin()
async def role_panel_cmd(interaction: discord.Interaction):
    await interaction.channel.send(embed=discord.Embed(title="ロール選択", description="ボタンでロールを付与・解除できます。右端の解除ボタンは対象4ロールのみを外します。"),
                                   view=RolePanelView())
    await safe_ephemeral(interaction, "ロールパネルを設置しました。")

@bot.tree.command(name="tournament", description="大会作成モーダルを開く")
@is_admin()
async def tournament_cmd(interaction: discord.Interaction):
    await interaction.response.send_modal(TournamentCreateModal())

@bot.tree.command(name="daily_report", description="昨日の活動報告を表示")
@is_admin()
async def daily_report_cmd(interaction: discord.Interaction):
    today = datetime.now(JST).date()
    start = datetime.combine(today-timedelta(days=1), time.min, tzinfo=JST)
    await safe_ephemeral(interaction, build_daily_report(start, start+timedelta(days=1)))

@bot.tree.command(name="activity_stats", description="指定期間の活動統計")
@app_commands.describe(days="集計日数（1〜90）")
@is_admin()
async def activity_stats_cmd(interaction: discord.Interaction, days: app_commands.Range[int,1,90]=7):
    await safe_ephemeral(interaction, report_for_period(days))

@bot.tree.command(name="bot_status", description="Bot稼働状況")
@is_admin()
async def bot_status_cmd(interaction: discord.Interaction):
    with connect() as con:
        counts = {t: con.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]
                  for t in ("recruitment_posts","recruitment_participants","vc_sessions","tournaments")}
    latency = round(bot.latency*1000)
    await safe_ephemeral(interaction, f"稼働中｜Ping {latency}ms\nDB: {counts}")

@bot.tree.command(name="admin_panel", description="運営向け機能一覧")
@is_admin()
async def admin_panel_cmd(interaction: discord.Interaction):
    await safe_ephemeral(interaction, "運営コマンド: /setup /fa_card /recruit_panel /team_panel /matching_panel /role_panel /tournament /daily_report /activity_stats /bot_status /admin_panel /operation_logs")

@bot.tree.command(name="operation_logs", description="直近の運営ログ")
@is_admin()
async def operation_logs_cmd(interaction: discord.Interaction):
    with connect() as con:
        rows = con.execute("SELECT actor_id,action,detail,created_at FROM operation_logs ORDER BY id DESC LIMIT 15").fetchall()
    desc = "\n".join(f"{r['created_at'][:16]} <@{r['actor_id'] or 0}> {r['action']} {r['detail']}" for r in rows) or "ログはありません。"
    await safe_ephemeral(interaction, desc[:1900])

@bot.tree.error
async def app_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "このコマンドはサーバー管理者のみ実行できます。"
    else:
        LOG.exception("Application command failed", exc_info=error)
        msg = "コマンド実行中にエラーが発生しました。Botログを確認してください。"
    await safe_ephemeral(interaction, msg)

# ---------------- HTTP health endpoint (Render) ----------------
async def health(_request):
    return web.Response(text="Nexus League Bot v5 is running", status=200)

async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    LOG.info("Health server listening on %s", PORT)

async def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN environment variable is required")
    init_db()
    await start_health_server()
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
