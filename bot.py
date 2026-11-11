
"""
Nexus League Bot v5.2
Python 3.10+ / discord.py 2.x
SQLite stores operational data only.
Player registration details (including Riot ID) are NEVER written to SQLite.
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


# ============================================================
# 1. 基本設定
# ============================================================

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
TOURNAMENT_CHANNEL_ID = 1566061702716329994

ROLE_NAMES = ("ノーマル", "ランク", "カスタム", "大会")

TEAM_CATEGORY_ID = int(os.getenv("TEAM_CATEGORY_ID", "0")) or None
MATCHING_CATEGORY_ID = int(os.getenv("MATCHING_CATEGORY_ID", "0")) or None
OPERATIONS_ROLE_ID = int(os.getenv("OPERATIONS_ROLE_ID", "0")) or None

JST = ZoneInfo("Asia/Tokyo")
PORT = int(os.getenv("PORT", "10000"))

LOG = logging.getLogger("nexus")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


# ============================================================
# 2. ランク・ポイント設定
# ============================================================

RANKS = [
    ("CHALLENGER", "Challenger", 8),
    ("GRANDMASTER", "Grandmaster", 7),
    ("MASTER", "Master", 6),
    ("DIAMOND_1_2", "Diamond I-II", 5),
    ("DIAMOND_3_4", "Diamond III-IV", 4),
    ("EMERALD_1_2", "Emerald I-II", 3),
    ("EMERALD_3_4", "Emerald III-IV", 2),
    ("PLATINUM", "Platinum I-IV", 1),
    ("COACH", "コーチ", 0),
]

RANK_LABELS = {key: label for key, label, points in RANKS}
RANK_POINTS = {key: points for key, label, points in RANKS}

LANES = ("TOP", "JGL", "MID", "ADC", "SUP", "コーチ")

RECRUIT_KIND_LABELS = {
    "normal": "ノーマル・ARAM",
    "duo": "デュオランク",
    "flex": "フレックス",
    "custom": "カスタム",
}

ROLE_MENTION_NAMES = {
    "normal": "ノーマル",
    "duo": "ランク",
    "flex": "ランク",
    "custom": "カスタム",
}


# ============================================================
# 3. データベース
# ============================================================

def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db() -> None:
    with connect() as con:

        # 登録情報をDBに保存しない方針のため、旧playersテーブルを削除
        con.execute("DROP TABLE IF EXISTS players")

        con.execute("""
        CREATE TABLE IF NOT EXISTS recruitment_posts(
            message_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            thread_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS recruitment_participants(
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL
                CHECK(status IN ('regular','late')),
            joined_at TEXT NOT NULL,
            PRIMARY KEY(message_id,user_id),
            FOREIGN KEY(message_id)
                REFERENCES recruitment_posts(message_id)
                ON DELETE CASCADE
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS vc_sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            joined_at TEXT NOT NULL,
            left_at TEXT
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS vc_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            event TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS tournaments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            creator_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            deadline_at TEXT,
            rules TEXT NOT NULL,
            entry_type TEXT NOT NULL,
            status TEXT NOT NULL,
            channel_id INTEGER,
            message_id INTEGER,
            created_at TEXT NOT NULL
        )
        """)

        # 既存DBにdeadline_atがない場合の追加
        columns = {
            row["name"]
            for row in con.execute(
                "PRAGMA table_info(tournaments)"
            ).fetchall()
        }

        if "deadline_at" not in columns:
            con.execute(
                "ALTER TABLE tournaments ADD COLUMN deadline_at TEXT"
            )

        con.execute("""
        CREATE TABLE IF NOT EXISTS tournament_entries(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            team_name TEXT NOT NULL,
            members TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(tournament_id,user_id),
            FOREIGN KEY(tournament_id)
                REFERENCES tournaments(id)
                ON DELETE CASCADE
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS operation_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            actor_id INTEGER,
            action TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

        con.execute("""
        CREATE INDEX IF NOT EXISTS idx_vc_user_time
        ON vc_sessions(user_id,joined_at,left_at)
        """)

        con.execute("""
        CREATE INDEX IF NOT EXISTS idx_recruit_created
        ON recruitment_posts(created_at)
        """)


# ============================================================
# 4. 共通処理
# ============================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_action(
    guild_id: Optional[int],
    actor_id: Optional[int],
    action: str,
    detail: str = ""
) -> None:
    with connect() as con:
        con.execute(
            """
            INSERT INTO operation_logs
            (guild_id,actor_id,action,detail,created_at)
            VALUES(?,?,?,?,?)
            """,
            (
                guild_id,
                actor_id,
                action,
                detail[:1500],
                now_iso()
            )
        )


def is_admin():
    return app_commands.checks.has_permissions(
        administrator=True
    )


async def safe_ephemeral(
    interaction: discord.Interaction,
    content: str
):
    if interaction.response.is_done():
        await interaction.followup.send(
            content,
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            content,
            ephemeral=True
        )


def get_rank_label(rank_key: str) -> str:
    return RANK_LABELS.get(rank_key, rank_key)


def get_rank_points(rank_key: str) -> int:
    return RANK_POINTS.get(rank_key, 0)


def parse_jst_datetime(value: str) -> Optional[datetime]:
    try:
        result = datetime.strptime(
            value.strip(),
            "%Y-%m-%d %H:%M"
        )
        return result.replace(tzinfo=JST)
    except ValueError:
        return None



# ============================================================
# 5. プレイヤー登録
# ============================================================

class RegistrationModal(
    discord.ui.Modal,
    title="プレイヤー登録情報"
):
    riot_id = discord.ui.TextInput(
        label="Riot ID（名前#タグ）",
        placeholder="例：Player#JP1",
        max_length=100
    )

    role = discord.ui.TextInput(
        label="メインロール（TOP/JGL/MID/ADC/SUP/コーチ）",
        placeholder="例：MID",
        max_length=20
    )

    intro = discord.ui.TextInput(
        label="自己PR・得意チャンピオン",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=900
    )

    def __init__(self, rank_key: str):
        super().__init__()
        self.rank_key = rank_key

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):
        riot = self.riot_id.value.strip()
        role = self.role.value.strip().upper()

        if "#" not in riot or not all(
            riot.split("#", 1)
        ):
            return await safe_ephemeral(
                interaction,
                "Riot IDは「名前#タグ」の形式で入力してください。"
            )

        if role not in LANES:
            return await safe_ephemeral(
                interaction,
                "ロールはTOP / JGL / MID / ADC / SUP / コーチから入力してください。"
            )

        if interaction.guild is None:
            return await safe_ephemeral(
                interaction,
                "サーバー内から登録してください。"
            )

        channel = interaction.guild.get_channel(
            REGISTRATION_CHANNEL_ID
        )

        if channel is None:
            try:
                channel = await interaction.guild.fetch_channel(
                    REGISTRATION_CHANNEL_ID
                )
            except discord.HTTPException:
                channel = None

        if not isinstance(
            channel,
            (discord.TextChannel, discord.Thread)
        ):
            return await safe_ephemeral(
                interaction,
                "登録情報の送信先が見つかりません。登録は完了していません。"
            )

        rank_label = get_rank_label(self.rank_key)
        rank_points = get_rank_points(self.rank_key)

        embed = discord.Embed(
            title="プレイヤー登録申請",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="Discord",
            value=f"{interaction.user.mention}",
            inline=False
        )

        embed.add_field(
            name="Riot ID",
            value=discord.utils.escape_markdown(riot),
            inline=True
        )

        embed.add_field(
            name="最高ランク",
            value=rank_label,
            inline=True
        )

        embed.add_field(
            name="ランクポイント",
            value=f"{rank_points} pt",
            inline=True
        )

        embed.add_field(
            name="メインロール",
            value=role,
            inline=True
        )

        embed.add_field(
            name="自己PR",
            value=self.intro.value.strip() or "未記入",
            inline=False
        )

        embed.set_footer(
            text="登録情報はBotのデータベースには保存されません。"
        )

        try:
            await channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none()
            )

        except (discord.Forbidden, discord.HTTPException):
            LOG.exception(
                "Registration submission failed"
            )

            return await safe_ephemeral(
                interaction,
                "登録情報の送信に失敗しました。登録は完了していません。運営に連絡してください。"
            )

        await safe_ephemeral(
            interaction,
            "登録情報を運営チャンネルへ送信しました。運営の確認をお待ちください。"
        )


# ============================================================
# 6. ランク選択メニュー
# ============================================================

class RankSelect(discord.ui.Select):

    def __init__(self):
        options = []

        for key, label, points in RANKS:
            options.append(
                discord.SelectOption(
                    label=f"{label}（{points}pt）",
                    value=key,
                    description=f"ランクポイント：{points}pt"
                )
            )

        super().__init__(
            placeholder="最高ランクを選択してください",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):
        selected_rank = self.values[0]

        await interaction.response.send_modal(
            RegistrationModal(selected_rank)
        )


class RankSelectView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(RankSelect())


# ============================================================
# 7. プレイヤー登録パネル
# ============================================================

class RegistrationPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="プレイヤー登録",
        style=discord.ButtonStyle.success,
        emoji="📝",
        custom_id="nexus:v52:registration:open"
    )
    async def open_registration(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "最高ランクを選択してください。",
            view=RankSelectView(),
            ephemeral=True
        )


# ============================================================
# 8. FA選手カード
# ============================================================

class FaModal(
    discord.ui.Modal,
    title="FA選手カード"
):

    riot = discord.ui.TextInput(
        label="Riot ID（名前#タグ）",
        placeholder="例：Player#JP1",
        max_length=100
    )

    rank = discord.ui.TextInput(
        label="ランク",
        placeholder="例：Diamond I",
        max_length=60
    )

    role = discord.ui.TextInput(
        label="メインロール",
        placeholder="例：MID",
        max_length=20
    )

    intro = discord.ui.TextInput(
        label="自己PR・得意チャンピオン",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=900
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):
        riot = self.riot.value.strip()

        if "#" not in riot or not all(
            riot.split("#", 1)
        ):
            return await safe_ephemeral(
                interaction,
                "Riot IDは「名前#タグ」の形式で入力してください。"
            )

        if interaction.guild is None:
            return await safe_ephemeral(
                interaction,
                "サーバー内から操作してください。"
            )

        channel = interaction.channel

        if not isinstance(
            channel,
            (discord.TextChannel, discord.Thread)
        ):
            return await safe_ephemeral(
                interaction,
                "このチャンネルには投稿できません。"
            )

        embed = discord.Embed(
            title="🌟 FA選手カード",
            description="選手募集・チーム加入希望",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.set_author(
            name=f"{riot}｜{self.rank.value}｜{self.role.value}",
            icon_url=interaction.user.display_avatar.url
        )

        embed.add_field(
            name="Riot ID",
            value=discord.utils.escape_markdown(riot),
            inline=True
        )

        embed.add_field(
            name="ランク",
            value=self.rank.value,
            inline=True
        )

        embed.add_field(
            name="メインロール",
            value=self.role.value,
            inline=True
        )

        embed.add_field(
            name="自己PR",
            value=self.intro.value.strip() or "未記入",
            inline=False
        )

        embed.set_footer(
            text=f"投稿者：{interaction.user}"
        )

        try:
            await channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none()
            )

        except (discord.Forbidden, discord.HTTPException):
            LOG.exception("FA card submission failed")

            return await safe_ephemeral(
                interaction,
                "FAカードを投稿できませんでした。"
            )

        await safe_ephemeral(
            interaction,
            "FAカードを投稿しました。"
        )


# ============================================================
# 9. FAカード管理パネル
# ============================================================

class FaPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="FA選手カードを作成",
        style=discord.ButtonStyle.primary,
        emoji="🌟",
        custom_id="nexus:v52:fa:create"
    )
    async def create_fa_card(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            FaModal()
        )


# ============================================================
# 10. チーム関連の非公開申請フォーム
# ============================================================

class PrivateRequestModal(
    discord.ui.Modal
):

    def __init__(self, request_type: str):
        self.request_type = request_type

        settings = {
            "team_create": {
                "title": "チーム結成申請",
                "channel": "チーム結成",
                "category_id": TEAM_CATEGORY_ID,
                "first_label": "チーム名",
                "first_placeholder": "結成するチーム名",
                "second_label": "募集メンバー・希望条件",
                "second_placeholder": "募集ロール、ランク、活動時間など"
            },
            "team_disband": {
                "title": "チーム解散申請",
                "channel": "チーム解散",
                "category_id": TEAM_CATEGORY_ID,
                "first_label": "チーム名",
                "first_placeholder": "解散するチーム名",
                "second_label": "解散理由・連絡事項",
                "second_placeholder": "運営への連絡事項"
            },
            "matching": {
                "title": "マッチング希望申請",
                "channel": "マッチング希望",
                "category_id": MATCHING_CATEGORY_ID,
                "first_label": "希望するロール・ランク",
                "first_placeholder": "例：MID / Diamond",
                "second_label": "希望条件・自己PR",
                "second_placeholder": "希望するチーム、活動時間、自己PRなど"
            }
        }

        self.settings = settings[request_type]

        super().__init__(
            title=self.settings["title"]
        )

        self.first_input = discord.ui.TextInput(
            label=self.settings["first_label"],
            placeholder=self.settings["first_placeholder"],
            max_length=100,
            required=True
        )

        self.second_input = discord.ui.TextInput(
            label=self.settings["second_label"],
            placeholder=self.settings["second_placeholder"],
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True
        )

        self.add_item(self.first_input)
        self.add_item(self.second_input)

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):
        guild = interaction.guild

        if guild is None:
            return await safe_ephemeral(
                interaction,
                "サーバー内から申請してください。"
            )

        category_id = self.settings["category_id"]
        category = None

        if category_id:
            category = guild.get_channel(category_id)

            if category is None:
                try:
                    category = await guild.fetch_channel(
                        category_id
                    )
                except discord.HTTPException:
                    category = None

            if not isinstance(
                category,
                discord.CategoryChannel
            ):
                return await safe_ephemeral(
                    interaction,
                    "申請先のカテゴリーが見つかりません。運営に連絡してください。"
                )

        bot_member = guild.me

        if bot_member is None:
            return await safe_ephemeral(
                interaction,
                "Botのサーバー情報を取得できませんでした。"
            )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True
            )
        }

        if OPERATIONS_ROLE_ID:
            operations_role = guild.get_role(
                OPERATIONS_ROLE_ID
            )

            if operations_role is not None:
                overwrites[operations_role] = (
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    )
                )

        embed = discord.Embed(
            title=self.settings["title"],
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name=self.settings["first_label"],
            value=self.first_input.value.strip(),
            inline=False
        )

        embed.add_field(
            name=self.settings["second_label"],
            value=self.second_input.value.strip(),
            inline=False
        )

        embed.add_field(
            name="申請者",
            value=interaction.user.mention,
            inline=False
        )

        try:
            channel = await guild.create_text_channel(
                name=self.settings["channel"],
                category=category,
                overwrites=overwrites,
                topic=(
                    f"{self.settings['title']}｜"
                    f"申請者ID：{interaction.user.id}"
                ),
                reason=(
                    f"{self.settings['title']} "
                    f"by {interaction.user}"
                )
            )

            await channel.send(
                content=interaction.user.mention,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                    roles=False,
                    everyone=False
                )
            )

        except discord.Forbidden:
            LOG.exception(
                "Private request channel permission error"
            )

            return await safe_ephemeral(
                interaction,
                "申請チャンネルを作成できませんでした。Botにチャンネル管理権限があるか確認してください。"
            )

        except discord.HTTPException:
            LOG.exception(
                "Private request channel creation failed"
            )

            return await safe_ephemeral(
                interaction,
                "申請チャンネルの作成に失敗しました。時間をおいて再度お試しください。"
            )

        await safe_ephemeral(
            interaction,
            f"申請を受け付けました。\n"
            f"専用チャンネルはこちらです：{channel.mention}"
        )


# ============================================================
# 11. チーム結成・チーム解散パネル
# ============================================================

class TeamPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="チームを結成する",
        style=discord.ButtonStyle.success,
        emoji="🛡️",
        custom_id="nexus:v52:team:create"
    )
    async def team_create(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            PrivateRequestModal("team_create")
        )

    @discord.ui.button(
        label="チームを解散する",
        style=discord.ButtonStyle.danger,
        emoji="🗑️",
        custom_id="nexus:v52:team:disband"
    )
    async def team_disband(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            PrivateRequestModal("team_disband")
        )


# ============================================================
# 12. マッチング希望パネル
# ============================================================

class MatchingPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="マッチングを希望する",
        style=discord.ButtonStyle.primary,
        emoji="🤝",
        custom_id="nexus:v52:matching:request"
    )
    async def matching_request(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            PrivateRequestModal("matching")
        )


# ============================================================
# 13. 大会参加・辞退用モーダル
# ============================================================

class TournamentTeamModal(
    discord.ui.Modal
):

    def __init__(
        self,
        tournament_id: int,
        action: str
    ):
        self.tournament_id = tournament_id
        self.action = action

        if action == "join":
            title = "大会に参加する"
            label = "参加するチーム名"
            placeholder = "登録するチーム名を正確に入力してください"
        else:
            title = "大会を辞退する"
            label = "辞退するチーム名"
            placeholder = "参加登録時と完全に同じチーム名を入力してください"

        super().__init__(title=title)

        self.team_name = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            max_length=100,
            required=True
        )

        self.add_item(self.team_name)

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):
        team_name = self.team_name.value.strip()

        if not team_name:
            return await safe_ephemeral(
                interaction,
                "チーム名を入力してください。"
            )

        with connect() as conn:
            tournament = conn.execute(
                """
                SELECT *
                FROM tournaments
                WHERE id = ?
                """,
                (self.tournament_id,)
            ).fetchone()

        if tournament is None:
            return await safe_ephemeral(
                interaction,
                "大会情報が見つかりません。"
            )

        if tournament["status"] != "open":
            return await safe_ephemeral(
                interaction,
                "この大会は現在受付を終了しています。"
            )

        now = datetime.now(
            ZoneInfo("Asia/Tokyo")
        )

        deadline_text = tournament["deadline_at"]

        if deadline_text:
            try:
                deadline = datetime.fromisoformat(
                    deadline_text
                )

                if deadline.tzinfo is None:
                    deadline = deadline.replace(
                        tzinfo=ZoneInfo("Asia/Tokyo")
                    )

                if now > deadline:
                    return await safe_ephemeral(
                        interaction,
                        "この大会の参加締切を過ぎています。"
                    )

            except ValueError:
                LOG.exception(
                    "Invalid tournament deadline"
                )

                return await safe_ephemeral(
                    interaction,
                    "大会の締切情報を確認できません。運営に連絡してください。"
                )

        if self.action == "join":

            with connect() as conn:
                existing_team = conn.execute(
                    """
                    SELECT id
                    FROM tournament_entries
                    WHERE tournament_id = ?
                    AND team_name = ?
                    """,
                    (
                        self.tournament_id,
                        team_name
                    )
                ).fetchone()

                if existing_team is not None:
                    return await safe_ephemeral(
                        interaction,
                        "このチーム名はすでに参加登録されています。"
                    )

                existing_user = conn.execute(
                    """
                    SELECT id
                    FROM tournament_entries
                    WHERE tournament_id = ?
                    AND user_id = ?
                    """,
                    (
                        self.tournament_id,
                        interaction.user.id
                    )
                ).fetchone()

                if existing_user is not None:
                    return await safe_ephemeral(
                        interaction,
                        "あなたはすでにこの大会へ参加登録しています。"
                    )

                conn.execute(
                    """
                    INSERT INTO tournament_entries (
                        tournament_id,
                        user_id,
                        team_name,
                        members,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self.tournament_id,
                        interaction.user.id,
                        team_name,
                        "",
                        now_iso()
                    )
                )

            await refresh_tournament_message(
                self.tournament_id
            )

            await safe_ephemeral(
                interaction,
                f"「{team_name}」の大会参加登録が完了しました。"
            )

        else:

            with connect() as conn:
                existing_team = conn.execute(
                    """
                    SELECT id
                    FROM tournament_entries
                    WHERE tournament_id = ?
                    AND team_name = ?
                    """,
                    (
                        self.tournament_id,
                        team_name
                    )
                ).fetchone()

                if existing_team is None:
                    return await safe_ephemeral(
                        interaction,
                        "入力されたチーム名と完全一致する参加登録がありません。\n"
                        "チーム名の入力間違いがないか確認してください。"
                    )

                conn.execute(
                    """
                    DELETE FROM tournament_entries
                    WHERE tournament_id = ?
                    AND team_name = ?
                    """,
                    (
                        self.tournament_id,
                        team_name
                    )
                )

            await refresh_tournament_message(
                self.tournament_id
            )

            await safe_ephemeral(
                interaction,
                f"「{team_name}」の大会参加登録を取り消しました。"
            )


# ============================================================
# 14. 大会参加・辞退ボタン
# ============================================================

class TournamentPanelView(discord.ui.View):

    def __init__(
        self,
        tournament_id: int
    ):
        super().__init__(timeout=None)

        self.tournament_id = tournament_id

        join_button = discord.ui.Button(
            label="大会に参加する",
            style=discord.ButtonStyle.success,
            emoji="🏆",
            custom_id=(
                f"nexus:v52:tournament:{tournament_id}:join"
            )
        )

        withdraw_button = discord.ui.Button(
            label="辞退する",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            custom_id=(
                f"nexus:v52:tournament:{tournament_id}:withdraw"
            )
        )

        join_button.callback = self.join_callback
        withdraw_button.callback = self.withdraw_callback

        self.add_item(join_button)
        self.add_item(withdraw_button)

    async def join_callback(
        self,
        interaction: discord.Interaction
    ):
        await interaction.response.send_modal(
            TournamentTeamModal(
                self.tournament_id,
                "join"
            )
        )

    async def withdraw_callback(
        self,
        interaction: discord.Interaction
    ):
        await interaction.response.send_modal(
            TournamentTeamModal(
                self.tournament_id,
                "withdraw"
            )
        )


# ============================================================
# 15. 大会参加チーム一覧の取得
# ============================================================

def get_tournament_teams(
    tournament_id: int
) -> list[str]:

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT team_name
            FROM tournament_entries
            WHERE tournament_id = ?
            ORDER BY created_at ASC
            """,
            (tournament_id,)
        ).fetchall()

    teams = []

    for row in rows:
        name = row["team_name"]

        if name and name not in teams:
            teams.append(name)

    return teams


# ============================================================
# 16. 大会情報Embedの作成
# ============================================================

def build_tournament_embed(
    tournament,
    tournament_id: int
) -> discord.Embed:

    teams = get_tournament_teams(
        tournament_id
    )

    embed = discord.Embed(
        title=f"🏆 {tournament['name']}",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="開催日時",
        value=tournament["starts_at"],
        inline=False
    )

    embed.add_field(
        name="参加締切",
        value=(
            tournament["deadline_at"]
            or "未設定"
        ),
        inline=False
    )

    embed.add_field(
        name="大会ルール",
        value=(
            tournament["rules"]
            or "特になし"
        ),
        inline=False
    )

    if teams:
        team_text = "\n".join(
            f"{index}. {name}"
            for index, name in enumerate(
                teams,
                start=1
            )
        )
    else:
        team_text = "まだ参加チームはありません。"

    embed.add_field(
        name=f"参加チーム一覧（{len(teams)}チーム）",
        value=team_text[:4000],
        inline=False
    )

    embed.set_footer(
        text=f"大会ID：{tournament_id}｜チーム単位で参加登録"
    )

    return embed


# ============================================================
# 17. 大会投稿の更新
# ============================================================

async def refresh_tournament_message(
    tournament_id: int
):
    with connect() as conn:
        tournament = conn.execute(
            """
            SELECT *
            FROM tournaments
            WHERE id = ?
            """,
            (tournament_id,)
        ).fetchone()

    if tournament is None:
        return

    guild = bot.get_guild(
        tournament["guild_id"]
    )

    if guild is None:
        return

    channel = guild.get_channel(
        tournament["channel_id"]
    )

    if channel is None:
        try:
            channel = await guild.fetch_channel(
                tournament["channel_id"]
            )
        except discord.HTTPException:
            return

    if not isinstance(
        channel,
        (discord.TextChannel, discord.Thread)
    ):
        return

    try:
        message = await channel.fetch_message(
            tournament["message_id"]
        )

        embed = build_tournament_embed(
            tournament,
            tournament_id
        )

        await message.edit(
            embed=embed,
            view=TournamentPanelView(
                tournament_id
            )
        )

    except discord.NotFound:
        LOG.warning(
            "Tournament message not found: %s",
            tournament_id
        )

    except discord.HTTPException:
        LOG.exception(
            "Tournament message refresh failed: %s",
            tournament_id
        )


# ============================================================
# 18. 大会作成モーダル
# ============================================================

class TournamentCreateModal(
    discord.ui.Modal,
    title="大会を作成する"
):

    name = discord.ui.TextInput(
        label="大会名",
        placeholder="例：Nexus League Cup",
        max_length=100
    )

    starts_at = discord.ui.TextInput(
        label="開催日時（YYYY-MM-DD HH:MM）",
        placeholder="例：2026-12-01 20:00",
        max_length=16
    )

    deadline_at = discord.ui.TextInput(
        label="参加締切日時（YYYY-MM-DD HH:MM）",
        placeholder="例：2026-11-30 23:59",
        max_length=16
    )

    rules = discord.ui.TextInput(
        label="大会ルール",
        style=discord.TextStyle.paragraph,
        placeholder="大会のルールを入力してください。",
        required=False,
        max_length=1500
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):
        if interaction.guild is None:
            return await safe_ephemeral(
                interaction,
                "サーバー内から大会を作成してください。"
            )

        try:
            start_time = datetime.strptime(
                self.starts_at.value.strip(),
                "%Y-%m-%d %H:%M"
            ).replace(
                tzinfo=ZoneInfo("Asia/Tokyo")
            )

            deadline_time = datetime.strptime(
                self.deadline_at.value.strip(),
                "%Y-%m-%d %H:%M"
            ).replace(
                tzinfo=ZoneInfo("Asia/Tokyo")
            )

        except ValueError:
            return await safe_ephemeral(
                interaction,
                "日時は「2026-12-01 20:00」の形式で入力してください。"
            )

        now = datetime.now(
            ZoneInfo("Asia/Tokyo")
        )

        if deadline_time <= now:
            return await safe_ephemeral(
                interaction,
                "参加締切は現在より未来の日時にしてください。"
            )

        if deadline_time > start_time:
            return await safe_ephemeral(
                interaction,
                "参加締切は開催日時より前に設定してください。"
            )

        channel = interaction.guild.get_channel(
            TOURNAMENT_CHANNEL_ID
        )

        if channel is None:
            try:
                channel = await interaction.guild.fetch_channel(
                    TOURNAMENT_CHANNEL_ID
                )
            except discord.HTTPException:
                channel = None

        if not isinstance(
            channel,
            discord.TextChannel
        ):
            return await safe_ephemeral(
                interaction,
                "大会投稿先チャンネルが見つかりません。"
            )

        try:
            with connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO tournaments (
                        guild_id,
                        creator_id,
                        name,
                        starts_at,
                        rules,
                        entry_type,
                        status,
                        channel_id,
                        message_id,
                        created_at,
                        deadline_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        interaction.guild.id,
                        interaction.user.id,
                        self.name.value.strip(),
                        start_time.isoformat(),
                        self.rules.value.strip(),
                        "team",
                        "open",
                        channel.id,
                        0,
                        now_iso(),
                        deadline_time.isoformat()
                    )
                )

                tournament_id = cursor.lastrowid

            with connect() as conn:
                tournament = conn.execute(
                    """
                    SELECT *
                    FROM tournaments
                    WHERE id = ?
                    """,
                    (tournament_id,)
                ).fetchone()

            embed = build_tournament_embed(
                tournament,
                tournament_id
            )

            message = await channel.send(
                embed=embed,
                view=TournamentPanelView(
                    tournament_id
                ),
                allowed_mentions=discord.AllowedMentions.none()
            )

            with connect() as conn:
                conn.execute(
                    """
                    UPDATE tournaments
                    SET message_id = ?
                    WHERE id = ?
                    """,
                    (
                        message.id,
                        tournament_id
                    )
                )

            await log_action(
                interaction.guild.id,
                interaction.user.id,
                "tournament_create",
                f"大会ID：{tournament_id}｜大会名：{self.name.value.strip()}"
            )

        except Exception:
            LOG.exception(
                "Tournament creation failed"
            )

            return await safe_ephemeral(
                interaction,
                "大会の作成に失敗しました。運営に連絡してください。"
            )

        await safe_ephemeral(
            interaction,
            f"大会を作成しました。\n投稿先：{channel.mention}"
        )


# ============================================================
# 19. 募集投稿の参加状況を取得
# ============================================================

def get_recruitment_counts(
    message_id: int
) -> tuple[int, int]:

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM recruitment_participants
            WHERE message_id = ?
            GROUP BY status
            """,
            (message_id,)
        ).fetchall()

    regular = 0
    late = 0

    for row in rows:
        if row["status"] == "regular":
            regular = row["total"]
        elif row["status"] == "late":
            late = row["total"]

    return regular, late


# ============================================================
# 20. 募集投稿Embedの作成
# ============================================================

def build_recruitment_embed(
    title: str,
    description: str,
    message_id: int
) -> discord.Embed:

    regular, late = get_recruitment_counts(
        message_id
    )

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(
        name="通常参加",
        value=f"{regular}人",
        inline=True
    )

    embed.add_field(
        name="途中参加",
        value=f"{late}人",
        inline=True
    )

    embed.add_field(
        name="参加合計",
        value=f"{regular + late}人",
        inline=True
    )

    embed.set_footer(
        text=f"募集ID：{message_id}"
    )

    return embed


# ============================================================
# 21. 募集参加ボタン
# ============================================================

class RecruitmentView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    async def update_participant(
        self,
        interaction: discord.Interaction,
        status: str | None
    ):
        if interaction.message is None:
            return await safe_ephemeral(
                interaction,
                "募集投稿を確認できませんでした。"
            )

        message_id = interaction.message.id
        user_id = interaction.user.id

        with connect() as conn:
            post = conn.execute(
                """
                SELECT message_id
                FROM recruitment_posts
                WHERE message_id = ?
                """,
                (message_id,)
            ).fetchone()

            if post is None:
                return await safe_ephemeral(
                    interaction,
                    "この募集情報はデータベースに登録されていません。"
                )

            existing = conn.execute(
                """
                SELECT status
                FROM recruitment_participants
                WHERE message_id = ?
                AND user_id = ?
                """,
                (
                    message_id,
                    user_id
                )
            ).fetchone()

            if status is None:
                if existing is None:
                    return await safe_ephemeral(
                        interaction,
                        "あなたはこの募集に参加していません。"
                    )

                conn.execute(
                    """
                    DELETE FROM recruitment_participants
                    WHERE message_id = ?
                    AND user_id = ?
                    """,
                    (
                        message_id,
                        user_id
                    )
                )

                response_text = "募集への参加を辞退しました。"

            else:
                if existing is not None:
                    conn.execute(
                        """
                        UPDATE recruitment_participants
                        SET status = ?, joined_at = ?
                        WHERE message_id = ?
                        AND user_id = ?
                        """,
                        (
                            status,
                            now_iso(),
                            message_id,
                            user_id
                        )
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO recruitment_participants (
                            message_id,
                            user_id,
                            status,
                            joined_at
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            message_id,
                            user_id,
                            status,
                            now_iso()
                        )
                    )

                if status == "regular":
                    response_text = "通常参加として登録しました。"
                else:
                    response_text = "途中参加として登録しました。"

        try:
            with connect() as conn:
                post_info = conn.execute(
                    """
                    SELECT *
                    FROM recruitment_posts
                    WHERE message_id = ?
                    """,
                    (message_id,)
                ).fetchone()

            if post_info is not None:
                original_embed = (
                    interaction.message.embeds[0]
                    if interaction.message.embeds
                    else None
                )

                title = (
                    original_embed.title
                    if original_embed and original_embed.title
                    else "参加者募集"
                )

                description = (
                    original_embed.description
                    if original_embed and original_embed.description
                    else "参加希望者はボタンを押してください。"
                )

                updated_embed = build_recruitment_embed(
                    title,
                    description,
                    message_id
                )

                await interaction.message.edit(
                    embed=updated_embed,
                    view=RecruitmentView()
                )

        except discord.HTTPException:
            LOG.exception(
                "Recruitment message update failed"
            )

        await safe_ephemeral(
            interaction,
            response_text
        )

    @discord.ui.button(
        label="参加する",
        style=discord.ButtonStyle.success,
        emoji="🙋",
        custom_id="nexus:v52:recruit:join"
    )
    async def join(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.update_participant(
            interaction,
            "regular"
        )

    @discord.ui.button(
        label="途中参加する",
        style=discord.ButtonStyle.primary,
        emoji="⏰",
        custom_id="nexus:v52:recruit:late"
    )
    async def late_join(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.update_participant(
            interaction,
            "late"
        )

    @discord.ui.button(
        label="辞退する",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="nexus:v52:recruit:withdraw"
    )
    async def withdraw(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await self.update_participant(
            interaction,
            None
        )


# ============================================================
# 22. 募集投稿とスレッドの作成
# ============================================================

async def create_recruit_thread(
    channel: discord.TextChannel,
    author: discord.abc.User,
    content: str,
    kind: str = "normal",
    title: str | None = None
):
    if not isinstance(channel, discord.TextChannel):
        return None

    post_title = title or "参加者募集"

    description = (
        content.strip()
        or "参加希望者はボタンから登録してください。"
    )

    embed = discord.Embed(
        title=post_title,
        description=description,
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(
        name="募集作成者",
        value=author.mention,
        inline=False
    )

    try:
        message = await channel.send(
            embed=embed,
            view=RecruitmentView(),
            allowed_mentions=discord.AllowedMentions.none()
        )

        with connect() as conn:
            conn.execute(
                """
                INSERT INTO recruitment_posts (
                    message_id,
                    guild_id,
                    channel_id,
                    thread_id,
                    kind,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    channel.guild.id,
                    channel.id,
                    None,
                    kind,
                    now_iso()
                )
            )

        try:
            thread = await message.create_thread(
                name=f"{post_title}"[:100],
                auto_archive_duration=1440
            )

            with connect() as conn:
                conn.execute(
                    """
                    UPDATE recruitment_posts
                    SET thread_id = ?
                    WHERE message_id = ?
                    """,
                    (
                        thread.id,
                        message.id
                    )
                )

            await thread.send(
                "こちらは募集専用スレッドです。\n"
                "参加者同士の連絡はこちらで行ってください。"
            )

        except discord.HTTPException:
            LOG.exception(
                "Recruitment thread creation failed"
            )

        return message

    except Exception:
        LOG.exception(
            "Recruitment post creation failed"
        )

        return None


# ============================================================
# 23. カスタム募集作成モーダル
# ============================================================

class CustomRecruitModal(
    discord.ui.Modal,
    title="カスタム募集を作成"
):

    date_time = discord.ui.TextInput(
        label="開催日時",
        placeholder="例：2026-11-20 21:00",
        max_length=16
    )

    recruit_title = discord.ui.TextInput(
        label="募集タイトル",
        placeholder="例：カスタム参加者募集",
        max_length=100
    )

    details = discord.ui.TextInput(
        label="募集内容・ルール",
        style=discord.TextStyle.paragraph,
        placeholder="募集人数やルールなどを入力してください。",
        required=False,
        max_length=1000
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):
        if interaction.guild is None:
            return await safe_ephemeral(
                interaction,
                "サーバー内から操作してください。"
            )

        try:
            start_time = datetime.strptime(
                self.date_time.value.strip(),
                "%Y-%m-%d %H:%M"
            ).replace(
                tzinfo=ZoneInfo("Asia/Tokyo")
            )

        except ValueError:
            return await safe_ephemeral(
                interaction,
                "開催日時は「2026-11-20 21:00」の形式で入力してください。"
            )

        if start_time <= datetime.now(
            ZoneInfo("Asia/Tokyo")
        ):
            return await safe_ephemeral(
                interaction,
                "開催日時は現在より未来に設定してください。"
            )

        channel = interaction.guild.get_channel(
            CUSTOM_CHANNEL_ID
        )

        if channel is None:
            try:
                channel = await interaction.guild.fetch_channel(
                    CUSTOM_CHANNEL_ID
                )
            except discord.HTTPException:
                channel = None

        if not isinstance(
            channel,
            discord.TextChannel
        ):
            return await safe_ephemeral(
                interaction,
                "カスタム募集チャンネルが見つかりません。"
            )

        custom_role = discord.utils.get(
            interaction.guild.roles,
            name="カスタム"
        )

        role_mention = (
            custom_role.mention
            if custom_role is not None
            else ""
        )

        description = (
            f"**開催日時：** {start_time.strftime('%Y-%m-%d %H:%M')}\n"
            f"**募集者：** {interaction.user.mention}\n\n"
            f"{self.details.value.strip() or '詳細はスレッド内で確認してください。'}"
        )

        if custom_role is not None:
            allowed_mentions = discord.AllowedMentions(
                users=True,
                roles=[custom_role],
                everyone=False
            )
        else:
            allowed_mentions = discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False
            )

        try:
            message = await channel.send(
                content=role_mention,
                embed=discord.Embed(
                    title=self.recruit_title.value.strip(),
                    description=description,
                    color=discord.Color.purple(),
                    timestamp=datetime.now(timezone.utc)
                ),
                view=RecruitmentView(),
                allowed_mentions=allowed_mentions
            )

            with connect() as conn:
                conn.execute(
                    """
                    INSERT INTO recruitment_posts (
                        message_id,
                        guild_id,
                        channel_id,
                        thread_id,
                        kind,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message.id,
                        interaction.guild.id,
                        channel.id,
                        None,
                        "custom",
                        now_iso()
                    )
                )

            try:
                thread = await message.create_thread(
                    name=self.recruit_title.value.strip()[:100],
                    auto_archive_duration=1440
                )

                with connect() as conn:
                    conn.execute(
                        """
                        UPDATE recruitment_posts
                        SET thread_id = ?
                        WHERE message_id = ?
                        """,
                        (
                            thread.id,
                            message.id
                        )
                    )

                await thread.send(
                    "こちらはカスタム募集専用スレッドです。\n"
                    "参加者同士の連絡はこちらで行ってください。"
                )

            except discord.HTTPException:
                LOG.exception(
                    "Custom recruitment thread creation failed"
                )

            await log_action(
                interaction.guild.id,
                interaction.user.id,
                "custom_recruit_create",
                self.recruit_title.value.strip()
            )

            # カスタム募集が3件増えるごとに
            # 新しい募集ボタンを設置する
            with connect() as conn:
                count_row = conn.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM recruitment_posts
                    WHERE guild_id = ?
                    AND kind = 'custom'
                    """,
                    (interaction.guild.id,)
                ).fetchone()

            custom_count = count_row["total"]

            if custom_count % 3 == 0:
                await channel.send(
                    "次のカスタム募集はこちらから作成できます。",
                    view=CustomRecruitPanelView()
                )

        except Exception:
            LOG.exception(
                "Custom recruitment creation failed"
            )

            return await safe_ephemeral(
                interaction,
                "カスタム募集の作成に失敗しました。運営に連絡してください。"
            )

        await safe_ephemeral(
            interaction,
            f"カスタム募集を投稿しました。\n{message.jump_url}"
        )


# ============================================================
# 24. カスタム募集ボタンパネル
# ============================================================

class CustomRecruitPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="カスタム募集する",
        style=discord.ButtonStyle.primary,
        emoji="🎮",
        custom_id="nexus:v52:custom_recruit:create"
    )
    async def create_custom_recruit(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.send_modal(
            CustomRecruitModal()
        )


# ============================================================
# 25. ログ・Bot本体の準備
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

LOG = logging.getLogger("NexusLeagueBot")


def has_admin_access(
    interaction: discord.Interaction
) -> bool:
    if interaction.guild is None:
        return False

    if interaction.user.guild_permissions.administrator:
        return True

    if OPERATIONS_ROLE_ID:
        return any(
            role.id == OPERATIONS_ROLE_ID
            for role in interaction.user.roles
        )

    return False


# ============================================================
# 26. ボイスチャンネル活動記録テーブル
# ============================================================

def init_voice_activity_table():
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS voice_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                left_at TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_voice_activity_guild_joined
            ON voice_activity(guild_id, joined_at)
            """
        )


# ============================================================
# 27. Botクラス
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
intents.voice_states = True


class NexusBot(commands.Bot):

    async def setup_hook(self):

        # DB初期化
        init_db()
        init_voice_activity_table()

        # 永続ボタン登録
        self.add_view(
            RegistrationPanelView()
        )

        self.add_view(
            FaPanelView()
        )

        self.add_view(
            TeamPanelView()
        )

        self.add_view(
            MatchingPanelView()
        )

        self.add_view(
            CustomRecruitPanelView()
        )

        self.add_view(
            RecruitmentView()
        )

        self.add_view(
            RolePanelView()
        )

        # 作成済み大会のボタンを復元
        with connect() as conn:
            tournaments = conn.execute(
                """
                SELECT id
                FROM tournaments
                WHERE status = 'open'
                """
            ).fetchall()

        for tournament in tournaments:
            self.add_view(
                TournamentPanelView(
                    tournament["id"]
                )
            )

        # スラッシュコマンド同期
        try:
            synced = await self.tree.sync()

            LOG.info(
                "Slash commands synced: %s",
                len(synced)
            )

        except Exception:
            LOG.exception(
                "Slash command sync failed"
            )


bot = NexusBot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# 28. ロール付与パネル
# ============================================================

class RolePanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

        role_names = [
            "TOP",
            "JGL",
            "MID",
            "ADC",
            "SUP"
        ]

        for role_name in role_names:
            button = discord.ui.Button(
                label=role_name,
                style=discord.ButtonStyle.secondary,
                custom_id=f"nexus:v52:role:{role_name}"
            )

            async def callback(
                interaction: discord.Interaction,
                selected_role=role_name
            ):
                if interaction.guild is None:
                    return await safe_ephemeral(
                        interaction,
                        "サーバー内から操作してください。"
                    )

                role = discord.utils.get(
                    interaction.guild.roles,
                    name=selected_role
                )

                if role is None:
                    return await safe_ephemeral(
                        interaction,
                        f"「{selected_role}」ロールが見つかりません。"
                    )

                member = interaction.guild.get_member(
                    interaction.user.id
                )

                if member is None:
                    return await safe_ephemeral(
                        interaction,
                        "メンバー情報を取得できませんでした。"
                    )

                try:
                    if role in member.roles:
                        await member.remove_roles(
                            role,
                            reason="Nexus role panel"
                        )

                        result = (
                            f"「{selected_role}」ロールを解除しました。"
                        )

                    else:
                        await member.add_roles(
                            role,
                            reason="Nexus role panel"
                        )

                        result = (
                            f"「{selected_role}」ロールを付与しました。"
                        )

                    await safe_ephemeral(
                        interaction,
                        result
                    )

                except discord.Forbidden:
                    await safe_ephemeral(
                        interaction,
                        "ロールを変更できません。Botのロール位置と権限を確認してください。"
                    )

                except discord.HTTPException:
                    LOG.exception(
                        "Role update failed"
                    )

                    await safe_ephemeral(
                        interaction,
                        "ロール変更に失敗しました。"
                    )

            button.callback = callback
            self.add_item(button)


# ============================================================
# 29. ボイス活動記録
# ============================================================

@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState
):
    if member.bot:
        return

    if before.channel == after.channel:
        return

    current_time = now_iso()

    try:
        with connect() as conn:

            # 以前のVC滞在記録を終了
            if before.channel is not None:
                active = conn.execute(
                    """
                    SELECT id
                    FROM voice_activity
                    WHERE guild_id = ?
                    AND user_id = ?
                    AND left_at IS NULL
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (
                        member.guild.id,
                        member.id
                    )
                ).fetchone()

                if active is not None:
                    conn.execute(
                        """
                        UPDATE voice_activity
                        SET left_at = ?
                        WHERE id = ?
                        """,
                        (
                            current_time,
                            active["id"]
                        )
                    )

            # 新しいVC滞在記録を開始
            if after.channel is not None:
                conn.execute(
                    """
                    INSERT INTO voice_activity (
                        guild_id,
                        user_id,
                        channel_id,
                        joined_at,
                        left_at
                    )
                    VALUES (?, ?, ?, ?, NULL)
                    """,
                    (
                        member.guild.id,
                        member.id,
                        after.channel.id,
                        current_time
                    )
                )

        await log_action(
            member.guild.id,
            member.id,
            "voice_state_update",
            (
                f"退出：{before.channel.name if before.channel else 'なし'}"
                f"｜参加：{after.channel.name if after.channel else 'なし'}"
            )
        )

    except Exception:
        LOG.exception(
            "Voice activity recording failed"
        )


# ============================================================
# 30. 通常募集チャンネルの自動募集
# ============================================================

@bot.event
async def on_message(
    message: discord.Message
):
    if message.author.bot:
        return

    if message.guild is None:
        return

    channel_kind = None

    for kind, channel_id in RECRUIT_CHANNELS.items():
        if message.channel.id == channel_id:
            channel_kind = kind
            break

    if channel_kind is not None:
        if isinstance(
            message.channel,
            discord.TextChannel
        ):
            await create_recruit_thread(
                channel=message.channel,
                author=message.author,
                content=message.content,
                kind=channel_kind,
                title=f"{channel_kind.upper()} 募集"
            )

    await bot.process_commands(message)


# ============================================================
# 31. 日次活動レポート作成
# ============================================================

async def build_daily_report(
    guild: discord.Guild,
    target_date: date | None = None
) -> str:

    if target_date is None:
        target_date = datetime.now(
            ZoneInfo("Asia/Tokyo")
        ).date()

    day_start = datetime.combine(
        target_date,
        datetime.min.time()
    ).replace(
        tzinfo=ZoneInfo("Asia/Tokyo")
    )

    day_end = day_start + timedelta(days=1)

    start_text = day_start.isoformat()
    end_text = day_end.isoformat()

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                user_id,
                SUM(
                    (
                        julianday(
                            CASE
                                WHEN left_at IS NULL THEN ?
                                ELSE left_at
                            END
                        ) - julianday(joined_at)
                    ) * 1440
                ) AS total_minutes
            FROM voice_activity
            WHERE guild_id = ?
            AND joined_at < ?
            AND (
                left_at IS NULL
                OR left_at > ?
            )
            GROUP BY user_id
            ORDER BY total_minutes DESC
            LIMIT 15
            """,
            (
                now_iso(),
                guild.id,
                end_text,
                start_text
            )
        ).fetchall()

        recruit_row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM recruitment_posts
            WHERE guild_id = ?
            AND created_at >= ?
            AND created_at < ?
            """,
            (
                guild.id,
                start_text,
                end_text
            )
        ).fetchone()

        custom_row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM recruitment_posts
            WHERE guild_id = ?
            AND kind = 'custom'
            AND created_at >= ?
            AND created_at < ?
            """,
            (
                guild.id,
                start_text,
                end_text
            )
        ).fetchone()

    lines = [
        f"📊 **Nexus League 日次活動レポート**",
        f"対象日：{target_date.isoformat()}",
        "",
        f"募集投稿数：{recruit_row['total']}件",
        f"カスタム募集数：{custom_row['total']}件",
        "",
        "🎧 **VC活動時間ランキング**"
    ]

    if rows:
        for index, row in enumerate(
            rows,
            start=1
        ):
            member = guild.get_member(
                row["user_id"]
            )

            member_name = (
                member.display_name
                if member
                else f"ユーザーID：{row['user_id']}"
            )

            minutes = max(
                0,
                int(row["total_minutes"] or 0)
            )

            hours = minutes // 60
            remaining = minutes % 60

            lines.append(
                f"{index}. {member_name}：{hours}時間{remaining}分"
            )
    else:
        lines.append(
            "この日のVC活動記録はありません。"
        )

    return "\n".join(lines)


# ============================================================
# 32. 指定期間の活動レポート
# ============================================================

async def report_for_period(
    guild: discord.Guild,
    days: int = 7
) -> str:

    now = datetime.now(
        ZoneInfo("Asia/Tokyo")
    )

    start = now - timedelta(days=days)

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                user_id,
                SUM(
                    (
                        julianday(
                            CASE
                                WHEN left_at IS NULL THEN ?
                                ELSE left_at
                            END
                        ) - julianday(joined_at)
                    ) * 1440
                ) AS total_minutes
            FROM voice_activity
            WHERE guild_id = ?
            AND joined_at >= ?
            GROUP BY user_id
            ORDER BY total_minutes DESC
            LIMIT 20
            """,
            (
                now.isoformat(),
                guild.id,
                start.isoformat()
            )
        ).fetchall()

        recruit_row = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM recruitment_posts
            WHERE guild_id = ?
            AND created_at >= ?
            """,
            (
                guild.id,
                start.isoformat()
            )
        ).fetchone()

    lines = [
        f"📊 **過去{days}日間の活動レポート**",
        f"募集投稿数：{recruit_row['total']}件",
        "",
        "🎧 **VC活動時間ランキング**"
    ]

    for index, row in enumerate(
        rows,
        start=1
    ):
        member = guild.get_member(
            row["user_id"]
        )

        name = (
            member.display_name
            if member
            else f"ユーザーID：{row['user_id']}"
        )

        minutes = max(
            0,
            int(row["total_minutes"] or 0)
        )

        lines.append(
            f"{index}. {name}："
            f"{minutes // 60}時間{minutes % 60}分"
        )

    if not rows:
        lines.append(
            "活動記録はありません。"
        )

    return "\n".join(lines)


# ============================================================
# 33. 毎日9時の日次レポート
# ============================================================

@tasks.loop(
    time=time(
        hour=9,
        minute=0,
        tzinfo=ZoneInfo("Asia/Tokyo")
    )
)
async def daily_dm():

    for guild in bot.guilds:
        try:
            report = await build_daily_report(
                guild
            )

            user = bot.get_user(
                REPORT_USER_ID
            )

            if user is None:
                try:
                    user = await bot.fetch_user(
                        REPORT_USER_ID
                    )
                except discord.HTTPException:
                    user = None

            if user is not None:
                await user.send(report)

        except Exception:
            LOG.exception(
                "Daily report delivery failed"
            )


@daily_dm.before_loop
async def before_daily_dm():
    await bot.wait_until_ready()


# ============================================================
# 34. Bot起動イベント
# ============================================================

@bot.event
async def on_ready():

    LOG.info(
        "Nexus League Bot logged in as %s",
        bot.user
    )

    if not daily_dm.is_running():
        daily_dm.start()


# ============================================================
# 35. 管理者用：初期パネル設置
# ============================================================

@bot.tree.command(
    name="setup",
    description="プレイヤー登録パネルを設置します"
)
async def setup_command(
    interaction: discord.Interaction
):
    if not has_admin_access(interaction):
        return await safe_ephemeral(
            interaction,
            "このコマンドは管理者専用です。"
        )

    if not isinstance(
        interaction.channel,
        discord.TextChannel
    ):
        return await safe_ephemeral(
            interaction,
            "テキストチャンネルで実行してください。"
        )

    embed = discord.Embed(
        title="Nexus League｜プレイヤー登録",
        description=(
            "下のボタンからプレイヤー登録を行ってください。\n\n"
            "1. プレイヤー登録を押す\n"
            "2. 最高ランクを選択する\n"
            "3. Riot ID・ロール・自己PRを入力する\n"
            "4. 登録申請を送信する\n\n"
            "登録情報は運営チャンネルに送信されます。"
        ),
        color=discord.Color.blurple()
    )

    await interaction.channel.send(
        embed=embed,
        view=RegistrationPanelView()
    )

    await safe_ephemeral(
        interaction,
        "プレイヤー登録パネルを設置しました。"
    )


# ============================================================
# 36. 管理者用：FAカード
# ============================================================

@bot.tree.command(
    name="fa_card",
    description="FA選手カードを作成します"
)
async def fa_card_command(
    interaction: discord.Interaction
):
    if not has_admin_access(interaction):
        return await safe_ephemeral(
            interaction,
            "このコマンドは管理者専用です。"
        )

    await interaction.response.send_modal(
        FaModal()
    )


# ============================================================
# 37. 管理者用：カスタム募集パネル
# ============================================================

@bot.tree.command(
    name="recruit_panel",
    description="カスタム募集ボタンを設置します"
)
async def recruit_panel_command(
    interaction: discord.Interaction
):
    if not has_admin_access(interaction):
        return await safe_ephemeral(
            interaction,
            "このコマンドは管理者専用です。"
        )

    if interaction.guild is None:
        return await safe_ephemeral(
            interaction,
            "サーバー内から実行してください。"
        )

    channel = interaction.guild.get_channel(
        CUSTOM_CHANNEL_ID
    )

    if channel is None:
        try:
            channel = await interaction.guild.fetch_channel(
                CUSTOM_CHANNEL_ID
            )
        except discord.HTTPException:
            channel = None

    if not isinstance(
        channel,
        discord.TextChannel
    ):
        return await safe_ephemeral(
            interaction,
            "カスタム募集チャンネルが見つかりません。"
        )

    await channel.send(
        "カスタム募集を作成する場合は、下のボタンを押してください。",
        view=CustomRecruitPanelView()
    )

    await safe_ephemeral(
        interaction,
        f"カスタム募集パネルを設置しました：{channel.mention}"
    )


# ============================================================
# 38. 管理者用：チームパネル
# ============================================================

@bot.tree.command(
    name="team_panel",
    description="チーム結成・解散パネルを設置します"
)
async def team_panel_command(
    interaction: discord.Interaction
):
    if not has_admin_access(interaction):
        return await safe_ephemeral(
            interaction,
            "このコマンドは管理者専用です。"
        )

    if not isinstance(
        interaction.channel,
        discord.TextChannel
    ):
        return await safe_ephemeral(
            interaction,
            "テキストチャンネルで実行してください。"
        )

    embed = discord.Embed(
        title="🛡️ チーム管理",
        description=(
            "チームの結成・解散申請はこちらから行えます。\n\n"
            "チーム結成：新しいチームの申請\n"
            "チーム解散：既存チームの解散申請"
        ),
        color=discord.Color.blurple()
    )

    await interaction.channel.send(
        embed=embed,
        view=TeamPanelView()
    )

    await safe_ephemeral(
        interaction,
        "チームパネルを設置しました。"
    )


# ============================================================
# 39. 管理者用：マッチングパネル
# ============================================================

@bot.tree.command(
    name="matching_panel",
    description="マッチング希望パネルを設置します"
)
async def matching_panel_command(
    interaction: discord.Interaction
):
    if not has_admin_access(interaction):
        return await safe_ephemeral(
            interaction,
            "このコマンドは管理者専用です。"
        )

    if not isinstance(
        interaction.channel,
        discord.TextChannel
    ):
        return await safe_ephemeral(
            interaction,
            "テキストチャンネルで実行してください。"
        )

    embed = discord.Embed(
        title="🤝 マッチング希望",
        description=(
            "チーム加入やメンバー募集を希望する方は、"
            "下のボタンから申請してください。"
        ),
        color=discord.Color.blurple()
    )

    await interaction.channel.send(
        embed=embed,
        view=MatchingPanelView()
    )

    await safe_ephemeral(
        interaction,
        "マッチングパネルを設置しました。"
    )


# ============================================================
# 40. 管理者用：ロールパネル
# ============================================================

@bot.tree.command(
    name="role_panel",
    description="ロール選択パネルを設置します"
)
async def role_panel_command(
    interaction: discord.Interaction
):
    if not has_admin_access(interaction):
        return await safe_ephemeral(
            interaction,
            "このコマンドは管理者専用です。"
        )

    if not isinstance(
        interaction.channel,
        discord.TextChannel
    ):
        return await safe_ephemeral(
            interaction,
            "テキストチャンネルで実行してください。"
        )

    embed = discord.Embed(
        title="🎮 ロール選択",
        description=(
            "希望するロールのボタンを押してください。\n"
            "もう一度押すとロールを解除できます。"
        ),
        color=discord.Color.blurple()
    )

    await interaction.channel.send(
        embed=embed,
        view=RolePanelView()
    )

    await safe_ephemeral(
        interaction,
        "ロールパネルを設置しました。"
    )


# ============================================================
# 41. 管理者用：大会作成
# ============================================================

@bot.tree.command(
    name="tournament",
    description="チーム対抗大会を作成します"
)
async def tournament_command(
    interaction: discord.Interaction
):
    if not has_admin_access(interaction):
        return await safe_ephemeral(
            interaction,
            "このコマンドは管理者専用です。"
        )

    await interaction.response.send_modal(
        TournamentCreateModal()
    )


# ============================================================
# 42. 管理者用：日次レポート
# ============================================================

@bot.tree.command(
    name="daily_report",
    description="本日の活動レポートを表示します"
)
async def daily_report_command(
    interaction: discord.Interaction
):
    if not has_admin_access(interaction):
        return await safe_ephemeral(
            interaction,
            "このコマンドは管理者専用です。"
        )

    if interaction.guild is None:
        return await safe_ephemeral(
            interaction,
            "サーバー内から実行してください。"
        )

    await interaction.response.defer(
        ephemeral=True
    )

    report = await build_daily_report(
        interaction.guild
    )

    await interaction.followup.send(
        report,
        ephemeral=True
    )


# ============================================================
# 43. 管理者用：活動統計
# ============================================================

@bot.tree.command(
    name="activity_stats",
    description="過去の活動統計を表示します"
)
@app_commands.describe(
    days="集計する日数（1～90日）"
)
async def activity_stats_command(
    interaction: discord.Interaction,
    days: app_commands.Range[int, 1, 90] = 7
):
    if not has_admin_access(interaction):
        return await safe_ephemeral(
            interaction,
            "このコマンドは管理者専用です。"
        )

    if interaction.guild is None:
        return await safe_ephemeral(
            interaction,
            "サーバー内から実行してください。"
        )

    await interaction.response.defer(
        ephemeral=True
    )

    report = await report_for_period(
        interaction.guild,
        days
    )

    await interaction.followup.send(
        report,
        ephemeral=True
    )


# ============================================================
# 44. Bot稼働状況
# ============================================================

@bot.tree.command(
    name="bot_status",
    description="Botの稼働状況を確認します"
)
async def bot_status_command(
    interaction: discord.Interaction
):
    if not has_admin_access(interaction):
        return await safe_ephemeral(
            interaction,
            "このコマンドは管理者専用です。"
        )

    latency = round(
        bot.latency * 1000
    )

    embed = discord.Embed(
        title="🤖 Nexus League Bot 稼働状況",
        color=discord.Color.green()
    )

    embed.add_field(
        name="状態",
        value="オンライン",
        inline=True
    )

    embed.add_field(
        name="Ping",
        value=f"{latency}ms",
        inline=True
    )

    embed.add_field(
        name="サーバー数",
        value=f"{len(bot.guilds)}",
        inline=True
    )

    embed.add_field(
        name="Discord.py",
        value=discord.__version__,
        inline=True
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ============================================================
# 45. 管理者パネル
# ============================================================

@bot.tree.command(
    name="admin_panel",
    description="管理者向けコマンド一覧を表示します"
)
async def admin_panel_command(
    interaction: discord.Interaction
):
    if not has_admin_access(interaction):
        return await safe_ephemeral(
            interaction,
            "このコマンドは管理者専用です。"
        )

    embed = discord.Embed(
        title="⚙️ Nexus League 管理者パネル",
        description=(
            "**パネル設置**\n"
            "`/setup` プレイヤー登録\n"
            "`/recruit_panel` カスタム募集\n"
            "`/team_panel` チーム結成・解散\n"
            "`/matching_panel` マッチング希望\n"
            "`/role_panel` ロール選択\n\n"
            "**大会管理**\n"
            "`/tournament` 大会作成\n\n"
            "**レポート・状態確認**\n"
            "`/daily_report` 日次レポート\n"
            "`/activity_stats` 活動統計\n"
            "`/bot_status` Bot稼働状況\n"
            "`/operation_logs` 操作ログ"
        ),
        color=discord.Color.blurple()
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ============================================================
# 46. 操作ログ表示
# ============================================================

@bot.tree.command(
    name="operation_logs",
    description="Botの操作ログを表示します"
)
@app_commands.describe(
    limit="表示件数（1～20件）"
)
async def operation_logs_command(
    interaction: discord.Interaction,
    limit: app_commands.Range[int, 1, 20] = 10
):
    if not has_admin_access(interaction):
        return await safe_ephemeral(
            interaction,
            "このコマンドは管理者専用です。"
        )

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM operation_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

    if not rows:
        return await safe_ephemeral(
            interaction,
            "操作ログはまだありません。"
        )

    lines = []

    for row in rows:
        lines.append(
            f"**{row['action']}**\n"
            f"ユーザーID：{row['user_id']}\n"
            f"詳細：{row['detail']}\n"
            f"日時：{row['created_at']}"
        )

    embed = discord.Embed(
        title="📋 操作ログ",
        description="\n\n".join(lines)[:4000],
        color=discord.Color.dark_grey()
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ============================================================
# 47. スラッシュコマンド共通エラー処理
# ============================================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    LOG.exception(
        "Application command error",
        exc_info=error
    )

    message = (
        "コマンドの実行中にエラーが発生しました。"
        "運営に連絡してください。"
    )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                message,
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                message,
                ephemeral=True
            )

    except discord.HTTPException:
        LOG.exception(
            "Could not send command error response"
        )


# ============================================================
# 48. Render用ヘルスチェック
# ============================================================

async def health_check(request):
    return web.Response(
        text="Nexus League Bot is running.",
        status=200
    )


async def start_health_server():

    app = web.Application()

    app.router.add_get(
        "/",
        health_check
    )

    app.router.add_get(
        "/health",
        health_check
    )

    runner = web.AppRunner(app)

    await runner.setup()

    port = int(
        os.getenv("PORT", "10000")
    )

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    LOG.info(
        "Health server started on port %s",
        port
    )

    return runner


# ============================================================
# 49. Bot起動処理
# ============================================================

async def main():

    token = os.getenv(
        "DISCORD_TOKEN"
    )

    if not token:
        raise RuntimeError(
            "環境変数 DISCORD_TOKEN が設定されていません。"
        )

    health_runner = await start_health_server()

    try:
        await bot.start(token)

    finally:
        await health_runner.cleanup()
        await bot.close()


# ============================================================
# 50. 実行
# ============================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        LOG.info(
            "Nexus League Bot stopped."
        )
