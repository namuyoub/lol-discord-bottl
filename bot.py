
"""
Nexus League Bot v5.2
Python 3.10+
discord.py 2.x
Render / SQLite

プレイヤー登録情報（Riot ID・自己紹介・OP.GG等）は
SQLiteには保存しません。
"""
from __future__ import annotations

import os
import re
import sqlite3
import logging
import asyncio
import unicodedata
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from aiohttp import web


# =========================================================
# 基本設定
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "nexus_league_v5.sqlite3")

GUILD_ID = int(os.getenv("GUILD_ID", "0")) or None

PORT = int(os.getenv("PORT", "10000"))

JST = ZoneInfo("Asia/Tokyo")

LOG = logging.getLogger("nexus")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO")
)

# 運営報告送信先
REPORT_USER_ID = 1392895521433321502

# プレイヤー登録情報の送信先
REGISTRATION_CHANNEL_ID = 1566055273146093599

# 通常・ランク募集チャンネル
RECRUIT_CHANNELS = {
    "normal": 1569643108147265709,
    "duo": 1569643437035229326,
    "flex": 1569643504994285,
}

# カスタム募集チャンネル
CUSTOM_CHANNEL_ID = 1567318455391101030

# 大会投稿先チャンネル
TOURNAMENT_CHANNEL_ID = 1566061702716329994

# チーム・マッチング用カテゴリ
TEAM_CATEGORY_ID = int(
    os.getenv("TEAM_CATEGORY_ID", "0")
) or None

MATCHING_CATEGORY_ID = int(
    os.getenv("MATCHING_CATEGORY_ID", "0")
) or None

# 運営ロール
OPERATIONS_ROLE_ID = int(
    os.getenv("OPERATIONS_ROLE_ID", "0")
) or None


# =========================================================
# ロール設定
# =========================================================

# ロールパネルで付与・解除する4種類
ROLE_NAMES = (
    "ノーマル",
    "ランク",
    "カスタム",
    "大会",
)

# 募集投稿でメンションするロール
ROLE_MENTION_NAMES = {
    "normal": "ノーマル",
    "duo": "ランク",
    "flex": "ランク",
    "custom": "カスタム",
}


# =========================================================
# ランク設定・ポイント
# =========================================================

RANKS = [
    ("CHALLENGER", "Challenger"),
    ("GRANDMASTER", "Grandmaster"),
    ("MASTER", "Master"),
    ("DIAMOND_1_2", "Diamond I-II"),
    ("DIAMOND_3_4", "Diamond III-IV"),
    ("EMERALD_1_2", "Emerald I-II"),
    ("EMERALD_3_4", "Emerald III-IV"),
    ("PLATINUM", "Platinum I-IV"),
    ("COACH", "Coach"),
]

RANK_POINTS = {
    "CHALLENGER": 8,
    "GRANDMASTER": 7,
    "MASTER": 6,
    "DIAMOND_1_2": 5,
    "DIAMOND_3_4": 4,
    "EMERALD_1_2": 3,
    "EMERALD_3_4": 2,
    "PLATINUM": 1,
    "COACH": 0,
}

# Discordニックネーム用のランク略称
RANK_SHORT_NAMES = {
    "CHALLENGER": "CH",
    "GRANDMASTER": "GM",
    "MASTER": "M",
    "DIAMOND_1_2": "D1-D2",
    "DIAMOND_3_4": "D3-D4",
    "EMERALD_1_2": "E1-E2",
    "EMERALD_3_4": "E3-E4",
    "PLATINUM": "P",
    "COACH": "Coach",
}

# プレイヤー登録時のポジション
LANES = (
    "TOP",
    "JGL",
    "MID",
    "ADC",
    "SUP",
)

# 募集の表示名
RECRUIT_KIND_LABELS = {
    "normal": "ノーマル・ARAM",
    "duo": "デュオランク",
    "flex": "フレックス",
    "custom": "カスタム",
}


# =========================================================
# データベース接続
# =========================================================

def connect() -> sqlite3.Connection:
    con = sqlite3.connect(
        DB_PATH,
        timeout=30
    )

    con.row_factory = sqlite3.Row

    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")

    return con


# =========================================================
# データベース初期化
# =========================================================

def init_db() -> None:

    with connect() as con:

        # 過去バージョンのプレイヤー登録情報を削除
        # Riot IDなどをDBに保存しないため
        con.execute(
            "DROP TABLE IF EXISTS players"
        )

        # 募集投稿の管理情報
        # 参加者の名前・参加状態はDBに保存しない
        con.execute("""
            CREATE TABLE IF NOT EXISTS recruitment_posts (
                message_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                thread_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # ボイスチャット利用記録
        con.execute("""
            CREATE TABLE IF NOT EXISTS vc_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                left_at TEXT
            )
        """)

        # ボイスチャット入退室履歴
        con.execute("""
            CREATE TABLE IF NOT EXISTS vc_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                event TEXT NOT NULL,
                occurred_at TEXT NOT NULL
            )
        """)

        # 大会情報
        con.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                rules TEXT NOT NULL,
                entry_type TEXT NOT NULL,
                status TEXT NOT NULL,
                channel_id INTEGER,
                message_id INTEGER,
                created_at TEXT NOT NULL,
                deadline TEXT,
                starts_display TEXT,
                deadline_display TEXT
            )
        """)

        # 大会エントリー情報
        con.execute("""
            CREATE TABLE IF NOT EXISTS tournament_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                team_name TEXT NOT NULL,
                members TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(tournament_id, user_id),
                FOREIGN KEY(tournament_id)
                    REFERENCES tournaments(id)
                    ON DELETE CASCADE
            )
        """)

        # 運営操作ログ
        con.execute("""
            CREATE TABLE IF NOT EXISTS operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                actor_id INTEGER,
                action TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # 既存DBにも大会締切・表示用日時の列を追加
        tournament_columns = {
            row["name"]
            for row in con.execute(
                "PRAGMA table_info(tournaments)"
            ).fetchall()
        }

        if "deadline" not in tournament_columns:
            con.execute(
                "ALTER TABLE tournaments ADD COLUMN deadline TEXT"
            )

        if "starts_display" not in tournament_columns:
            con.execute(
                "ALTER TABLE tournaments ADD COLUMN starts_display TEXT"
            )

        if "deadline_display" not in tournament_columns:
            con.execute(
                "ALTER TABLE tournaments ADD COLUMN deadline_display TEXT"
            )

        # 集計用インデックス
        con.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_vc_user_time
            ON vc_sessions(user_id, joined_at, left_at)
        """)

        con.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_recruit_created
            ON recruitment_posts(created_at)
        """)


# =========================================================
# 共通処理
# =========================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_jst() -> datetime:
    return datetime.now(JST)


def log_action(
    guild_id: Optional[int],
    actor_id: Optional[int],
    action: str,
    detail: str = ""
) -> None:

    with connect() as con:

        con.execute("""
            INSERT INTO operation_logs (
                guild_id,
                actor_id,
                action,
                detail,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            guild_id,
            actor_id,
            action,
            detail[:1500],
            now_iso()
        ))


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


# =========================================================
# 入力文字の統一
# 全角・半角の混在を許可する
# =========================================================

def normalize_input(value: str) -> str:

    return unicodedata.normalize(
        "NFKC",
        value.strip()
    )


# =========================================================
# Discordチャンネル取得
# =========================================================

async def get_text_channel(
    guild: discord.Guild,
    channel_id: int
):

    channel = guild.get_channel(channel_id)

    if channel is None:

        try:

            channel = await guild.fetch_channel(
                channel_id
            )

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException
        ):

            return None

    if isinstance(
        channel,
        (discord.TextChannel, discord.Thread)
    ):

        return channel

    return None


# =========================================================
# Discordメンバー名取得
# =========================================================

def get_member_display_name(
    member: discord.Member
) -> str:

    return member.display_name


# =========================================================
# Discordニックネーム作成
# =========================================================

def make_player_nickname(
    riot_id: str,
    positions: list[str],
    rank_key: str
) -> str:

    # Riot IDの # より前だけを使用
    game_name = riot_id.split("#", 1)[0].strip()

    # ポジションを連結
    position_text = "/".join(positions)

    # ランク略称
    rank_text = RANK_SHORT_NAMES.get(
        rank_key,
        rank_key
    )

    nickname = (
        f"{game_name} / "
        f"{position_text} / "
        f"{rank_text}"
    )

    # Discordのニックネーム上限
    return nickname[:32]


# =========================================================
# 日時表示用の共通処理
# =========================================================

def parse_custom_date(
    date_text: str,
    time_text: str
) -> tuple[datetime, str, str]:

    """
    月日と時間を別々に受け取る。

    例:
        11月22日
        21:00

    全角・半角のどちらでも入力可能。
    年は表示しない。
    """

    date_text = normalize_input(date_text)
    time_text = normalize_input(time_text)

    # 月日を抽出
    date_match = re.fullmatch(
        r"\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*",
        date_text
    )

    if not date_match:

        date_match = re.fullmatch(
            r"\s*(\d{1,2})\s*[/\-]\s*(\d{1,2})\s*",
            date_text
        )

    if not date_match:
        raise ValueError("日付形式が正しくありません。")

    month = int(date_match.group(1))
    day = int(date_match.group(2))

    # 時間を抽出
    time_match = re.fullmatch(
        r"\s*(\d{1,2})\s*:\s*(\d{2})\s*",
        time_text
    )

    if not time_match:
        raise ValueError("時間形式が正しくありません。")

    hour = int(time_match.group(1))
    minute = int(time_match.group(2))

    if hour > 23 or minute > 59:
        raise ValueError("時間が正しくありません。")

    current = now_jst()

    year = current.year

    try:

        target = datetime(
            year,
            month,
            day,
            hour,
            minute,
            tzinfo=JST
        )

    except ValueError:
        raise ValueError("存在しない日付です。")

    # 入力された月日が既に過ぎている場合は翌年扱い
    if target < current:

        target = datetime(
            year + 1,
            month,
            day,
            hour,
            minute,
            tzinfo=JST
        )

    date_display = f"{month}月{day}日"
    time_display = f"{hour:02d}:{minute:02d}"

    return (
        target,
        date_display,
        time_display
    )


# =========================================================
# Part 2
# 募集機能・参加ボタン・自動スレッド作成・カスタム募集
# =========================================================


# =========================================================
# 募集参加者の読み取り
# 参加者IDは募集メッセージ内のメンションとして保持する
# SQLiteには参加者情報を保存しない
# =========================================================

def get_recruitment_participants(
    embed: discord.Embed
) -> tuple[list[int], list[int]]:

    regular_ids = []
    late_ids = []

    for field in embed.fields:

        if field.name.startswith("参加する"):

            target = regular_ids

        elif field.name.startswith("途中参加する"):

            target = late_ids

        else:

            continue

        for match in re.findall(
            r"<@!?(\d+)>",
            field.value
        ):

            user_id = int(match)

            if user_id not in target:
                target.append(user_id)

    return regular_ids, late_ids


def make_participant_embed(
    original: discord.Embed,
    regular_ids: list[int],
    late_ids: list[int]
) -> discord.Embed:

    embed = discord.Embed.from_dict(
        original.to_dict()
    )

    embed.clear_fields()

    embed.add_field(
        name=f"参加する（{len(regular_ids)}名）",
        value="\n".join(
            f"<@{user_id}>"
            for user_id in regular_ids
        ) or "なし",
        inline=True
    )

    embed.add_field(
        name=f"途中参加する（{len(late_ids)}名）",
        value="\n".join(
            f"<@{user_id}>"
            for user_id in late_ids
        ) or "なし",
        inline=True
    )

    return embed


# =========================================================
# 募集投稿の管理情報を保存
# =========================================================

def save_recruitment_post(
    message: discord.Message,
    thread: discord.Thread,
    kind: str
) -> None:

    with connect() as con:

        con.execute("""
            INSERT OR REPLACE INTO recruitment_posts (
                message_id,
                guild_id,
                channel_id,
                thread_id,
                kind,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            message.id,
            message.guild.id,
            message.channel.id,
            thread.id,
            kind,
            now_iso()
        ))


# =========================================================
# 募集スレッド自動作成
# =========================================================

async def create_recruit_thread(
    message: discord.Message,
    kind: str
) -> discord.Thread:

    label = RECRUIT_KIND_LABELS.get(
        kind,
        "募集"
    )

    role_name = ROLE_MENTION_NAMES.get(kind)

    role = None

    if role_name and message.guild:

        role = discord.utils.get(
            message.guild.roles,
            name=role_name
        )

    thread = await message.create_thread(
        name=f"{label}｜{message.author.display_name}"[:100],
        auto_archive_duration=1440
    )

    mention = role.mention if role else ""

    await thread.send(
        f"{mention} {message.author.mention} さんの募集スレッドです。",
        allowed_mentions=discord.AllowedMentions(
            roles=[role] if role else [],
            users=True
        )
    )

    return thread


# =========================================================
# 募集参加ボタン
# =========================================================

class RecruitmentView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    async def _change(
        self,
        interaction: discord.Interaction,
        status: str
    ):

        if not interaction.guild or not interaction.message:

            return await safe_ephemeral(
                interaction,
                "サーバー内の募集投稿から操作してください。"
            )

        message = interaction.message

        if not message.embeds:

            return await safe_ephemeral(
                interaction,
                "募集情報を読み取れませんでした。"
            )

        with connect() as con:

            post = con.execute("""
                SELECT thread_id
                FROM recruitment_posts
                WHERE message_id=?
            """, (
                message.id,
            )).fetchone()

        if not post:

            return await safe_ephemeral(
                interaction,
                "募集情報が見つかりません。"
            )

        # 現在の参加者を募集メッセージから取得
        regular_ids, late_ids = get_recruitment_participants(
            message.embeds[0]
        )

        user_id = interaction.user.id

        # 一度両方から削除して状態を整理
        regular_ids = [
            uid for uid in regular_ids
            if uid != user_id
        ]

        late_ids = [
            uid for uid in late_ids
            if uid != user_id
        ]

        # 新しい参加状態を反映
        if status == "regular":

            regular_ids.append(user_id)

        elif status == "late":

            late_ids.append(user_id)

        # 辞退の場合は両方に追加しない
        embed = make_participant_embed(
            message.embeds[0],
            regular_ids,
            late_ids
        )

        try:

            await message.edit(
                embed=embed,
                view=self
            )

        except discord.HTTPException:

            LOG.exception(
                "Recruitment message update failed"
            )

            return await safe_ephemeral(
                interaction,
                "参加状況の更新に失敗しました。"
            )

        # スレッドを取得
        thread = interaction.guild.get_thread(
            post["thread_id"]
        )

        if thread is None:

            try:

                fetched = await interaction.guild.fetch_channel(
                    post["thread_id"]
                )

                if isinstance(fetched, discord.Thread):
                    thread = fetched

            except discord.HTTPException:

                thread = None

        # スレッドへの参加・退出
        if thread is not None:

            try:

                if status == "withdraw":

                    await thread.remove_user(
                        interaction.user
                    )

                    await thread.send(
                        f"🚪 {interaction.user.mention} さんが辞退しました。",
                        allowed_mentions=discord.AllowedMentions(
                            users=True
                        )
                    )

                else:

                    await thread.add_user(
                        interaction.user
                    )

                    label = (
                        "途中参加"
                        if status == "late"
                        else "通常参加"
                    )

                    await thread.send(
                        f"🙋 {interaction.user.mention} さんが{label}しました。",
                        allowed_mentions=discord.AllowedMentions(
                            users=True
                        )
                    )

            except discord.HTTPException:

                LOG.exception(
                    "Recruitment thread update failed"
                )

        # 操作結果
        if status == "withdraw":

            await safe_ephemeral(
                interaction,
                "辞退しました。再参加できます。"
            )

        elif status == "late":

            await safe_ephemeral(
                interaction,
                "途中参加を受け付けました。"
            )

        else:

            await safe_ephemeral(
                interaction,
                "参加を受け付けました。"
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

        await self._change(
            interaction,
            "regular"
        )

    @discord.ui.button(
        label="途中参加する",
        style=discord.ButtonStyle.primary,
        emoji="⏩",
        custom_id="nexus:v52:recruit:late"
    )
    async def late(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await self._change(
            interaction,
            "late"
        )

    @discord.ui.button(
        label="辞退する",
        style=discord.ButtonStyle.danger,
        emoji="🚪",
        custom_id="nexus:v52:recruit:withdraw"
    )
    async def withdraw(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await self._change(
            interaction,
            "withdraw"
        )


# =========================================================
# 通常・ランク募集の自動処理
# =========================================================

async def process_normal_recruitment(
    message: discord.Message,
    kind: str
):

    if not message.guild:
        return

    # 元の募集投稿からスレッドを作成
    thread = await create_recruit_thread(
        message,
        kind
    )

    role_name = ROLE_MENTION_NAMES.get(kind)

    role = discord.utils.get(
        message.guild.roles,
        name=role_name
    ) if role_name else None

    mention = role.mention if role else ""

    embed = discord.Embed(
        title=f"募集：{RECRUIT_KIND_LABELS[kind]}",
        description=message.content[:3500] or "募集内容なし",
        color=discord.Color.green()
    )

    embed.add_field(
        name="募集主",
        value=message.author.mention,
        inline=False
    )

    embed.add_field(
        name="参加する（0名）",
        value="なし",
        inline=True
    )

    embed.add_field(
        name="途中参加する（0名）",
        value="なし",
        inline=True
    )

    panel = await message.reply(
        content=f"{mention} 募集スレッド：{thread.mention}",
        embed=embed,
        view=RecruitmentView(),
        mention_author=False,
        allowed_mentions=discord.AllowedMentions(
            roles=[role] if role else [],
            users=True
        )
    )

    save_recruitment_post(
        panel,
        thread,
        kind
    )


# =========================================================
# カスタム募集の作成フォーム
# =========================================================

class CustomRecruitmentModal(
    discord.ui.Modal,
    title="カスタム募集を作成"
):

    date_input = discord.ui.TextInput(
        label="日程（月日）",
        placeholder="例：11月22日",
        max_length=20,
        required=True
    )

    time_input = discord.ui.TextInput(
        label="時間",
        placeholder="例：21:00",
        max_length=10,
        required=True
    )

    title_input = discord.ui.TextInput(
        label="募集タイトル",
        placeholder="例：フルパカスタム募集",
        max_length=100,
        required=True
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            return await safe_ephemeral(
                interaction,
                "サーバー内で操作してください。"
            )

        try:

            target, date_display, time_display = parse_custom_date(
                self.date_input.value,
                self.time_input.value
            )

        except ValueError as error:

            return await safe_ephemeral(
                interaction,
                str(error)
            )

        # 入力値をDiscord表示用に統一
        recruitment_title = normalize_input(
            self.title_input.value
        )

        channel = await get_text_channel(
            interaction.guild,
            CUSTOM_CHANNEL_ID
        )

        if not isinstance(channel, discord.TextChannel):

            return await safe_ephemeral(
                interaction,
                "カスタム募集チャンネルが見つかりません。"
            )

        role = discord.utils.get(
            interaction.guild.roles,
            name="カスタム"
        )

        role_mention = role.mention if role else ""

        # 日付と時間を大きく表示
        content = (
            f"{role_mention}\n"
            f"## {date_display}\n"
            f"## {time_display}"
        )

        embed = discord.Embed(
            title=recruitment_title,
            color=discord.Color.purple()
        )

        embed.add_field(
            name="参加する（0名）",
            value="なし",
            inline=True
        )

        embed.add_field(
            name="途中参加する（0名）",
            value="なし",
            inline=True
        )

        try:

            # 募集投稿
            post = await channel.send(
                content=content,
                embed=embed,
                view=RecruitmentView(),
                allowed_mentions=discord.AllowedMentions(
                    roles=[role] if role else []
                )
            )

            # カスタム募集にもスレッドを作成
            thread = await post.create_thread(
                name=f"カスタム｜{date_display} {time_display}"[:100],
                auto_archive_duration=1440
            )

            await thread.send(
                f"{interaction.user.mention} さんのカスタム募集スレッドです。",
                allowed_mentions=discord.AllowedMentions(
                    users=True
                )
            )

            save_recruitment_post(
                post,
                thread,
                "custom"
            )

        except discord.HTTPException:

            LOG.exception(
                "Custom recruitment creation failed"
            )

            return await safe_ephemeral(
                interaction,
                "カスタム募集の投稿に失敗しました。Botの権限を確認してください。"
            )

        # 投稿数を確認
        with connect() as con:

            count = con.execute("""
                SELECT COUNT(*) AS total
                FROM recruitment_posts
                WHERE kind='custom'
            """).fetchone()["total"]

        # 3件投稿されるごとに新しい募集ボタンを設置
        if count % 3 == 0:

            try:

                await channel.send(
                    embed=discord.Embed(
                        title="カスタム募集",
                        description="次のカスタム募集を作成できます。",
                        color=discord.Color.blurple()
                    ),
                    view=CustomRecruitmentPanelView()
                )

            except discord.HTTPException:

                LOG.exception(
                    "New custom recruitment panel creation failed"
                )

        await safe_ephemeral(
            interaction,
            "カスタム募集を投稿しました。"
        )


# =========================================================
# カスタム募集ボタン
# =========================================================

class CustomRecruitmentPanelView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(
        label="カスタム募集する",
        style=discord.ButtonStyle.success,
        emoji="🎮",
        custom_id="nexus:v52:custom:create"
    )
    async def create(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            CustomRecruitmentModal()
        )


# =========================================================
# Part 3
# プレイヤー登録・ランク選択・ポジション複数選択
# OP.GG送信・Discord表示名変更
# =========================================================


# =========================================================
# 登録情報の最終入力モーダル
# =========================================================

class RegistrationModal(
    discord.ui.Modal,
    title="プレイヤー情報登録"
):

    riot_id = discord.ui.TextInput(
        label="Riot ID",
        placeholder="例：Player#JP1",
        max_length=80,
        required=True
    )

    introduction = discord.ui.TextInput(
        label="自己紹介",
        placeholder="自己紹介を入力してください。",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )

    opgg_url = discord.ui.TextInput(
        label="OP.GGアドレス",
        placeholder="https://www.op.gg/...",
        max_length=300,
        required=True
    )

    def __init__(
        self,
        rank_key: str,
        positions: list[str]
    ):

        super().__init__()

        self.rank_key = rank_key
        self.positions = positions

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            return await safe_ephemeral(
                interaction,
                "サーバー内で登録してください。"
            )

        riot_id_value = normalize_input(
            self.riot_id.value
        )

        introduction_value = normalize_input(
            self.introduction.value
        )

        opgg_value = normalize_input(
            self.opgg_url.value
        )

        # Riot IDの形式確認
        if "#" not in riot_id_value:

            return await safe_ephemeral(
                interaction,
                "Riot IDは「名前#タグ」の形式で入力してください。"
            )

        game_name, tag_line = riot_id_value.split(
            "#",
            1
        )

        if not game_name.strip() or not tag_line.strip():

            return await safe_ephemeral(
                interaction,
                "Riot IDの名前とタグを正しく入力してください。"
            )

        # OP.GG URL確認
        if not re.match(
            r"^https?://",
            opgg_value,
            flags=re.IGNORECASE
        ):

            return await safe_ephemeral(
                interaction,
                "OP.GGアドレスは https:// から入力してください。"
            )

        if not re.search(
            r"(^|\.)op\.gg(/|$)",
            re.sub(
                r"^https?://",
                "",
                opgg_value,
                flags=re.IGNORECASE
            ),
            flags=re.IGNORECASE
        ):

            return await safe_ephemeral(
                interaction,
                "OP.GGのアドレスを入力してください。"
            )

        rank_label = dict(RANKS).get(
            self.rank_key
        )

        if not rank_label:

            return await safe_ephemeral(
                interaction,
                "ランク情報が正しくありません。最初からやり直してください。"
            )

        if not self.positions:

            return await safe_ephemeral(
                interaction,
                "ポジションを1つ以上選択してください。"
            )

        points = RANK_POINTS.get(
            self.rank_key,
            0
        )

        # 登録先チャンネル
        channel = await get_text_channel(
            interaction.guild,
            REGISTRATION_CHANNEL_ID
        )

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            return await safe_ephemeral(
                interaction,
                "プレイヤー登録チャンネルが見つかりません。"
            )

        # 登録情報をEmbedにまとめる
        embed = discord.Embed(
            title="プレイヤー登録",
            color=discord.Color.blue(),
            timestamp=now_jst()
        )

        embed.add_field(
            name="プレイヤー",
            value=interaction.user.mention,
            inline=False
        )

        embed.add_field(
            name="Riot ID",
            value=discord.utils.escape_markdown(
                riot_id_value
            ),
            inline=True
        )

        embed.add_field(
            name="ランク",
            value=rank_label,
            inline=True
        )

        embed.add_field(
            name="ランクポイント",
            value=f"{points} pt",
            inline=True
        )

        embed.add_field(
            name="ポジション",
            value=" / ".join(self.positions),
            inline=False
        )

        embed.add_field(
            name="自己紹介",
            value=introduction_value[:1024],
            inline=False
        )

        embed.add_field(
            name="OP.GG",
            value=f"[OP.GGを開く]({opgg_value})",
            inline=False
        )

        embed.set_footer(
            text=f"登録者ID：{interaction.user.id}"
        )

        # 先に登録投稿を送信する
        # 送信に失敗した場合は成功扱いにしない
        try:

            await channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    users=True
                )
            )

        except discord.Forbidden:

            LOG.exception(
                "Registration channel permission denied"
            )

            return await safe_ephemeral(
                interaction,
                "登録情報の送信に失敗しました。Botに登録チャンネルへの送信権限があるか確認してください。"
            )

        except discord.HTTPException:

            LOG.exception(
                "Registration post failed"
            )

            return await safe_ephemeral(
                interaction,
                "登録情報の送信に失敗しました。時間をおいて再度お試しください。"
            )

        # =================================================
        # Discordニックネーム変更
        # =================================================

        nickname = make_player_nickname(
            riot_id_value,
            self.positions,
            self.rank_key
        )

        nickname_changed = False

        nickname_error = None

        try:

            await interaction.user.edit(
                nick=nickname,
                reason="Nexus League プレイヤー登録"
            )

            nickname_changed = True

        except discord.Forbidden:

            nickname_error = (
                "ニックネーム変更権限がありません。"
                "Botのロール位置と権限を確認してください。"
            )

            LOG.warning(
                "Nickname change forbidden: user=%s",
                interaction.user.id
            )

        except discord.HTTPException:

            nickname_error = (
                "Discordのニックネーム変更に失敗しました。"
            )

            LOG.exception(
                "Nickname change failed"
            )

        # 登録情報そのものはDBに保存しない
        # ポイントもDBには保存しない

        log_action(
            interaction.guild.id,
            interaction.user.id,
            "player_registration",
            "プレイヤー登録投稿を送信"
        )

        if nickname_changed:

            await safe_ephemeral(
                interaction,
                "プレイヤー登録が完了しました！\n"
                f"Discord表示名を「{nickname}」に変更しました。"
            )

        else:

            await safe_ephemeral(
                interaction,
                "登録情報の送信は完了しました！\n"
                "ただし、Discord表示名の変更はできませんでした。\n"
                f"理由：{nickname_error}"
            )


# =========================================================
# ポジション複数選択メニュー
# =========================================================

class PositionSelect(
    discord.ui.Select
):

    def __init__(
        self,
        rank_key: str
    ):

        self.rank_key = rank_key

        options = [
            discord.SelectOption(
                label="TOP",
                value="TOP",
                description="トップ"
            ),
            discord.SelectOption(
                label="JUNGLE",
                value="JGL",
                description="ジャングル"
            ),
            discord.SelectOption(
                label="MID",
                value="MID",
                description="ミッド"
            ),
            discord.SelectOption(
                label="ADC",
                value="ADC",
                description="ボット・ADC"
            ),
            discord.SelectOption(
                label="SUPPORT",
                value="SUP",
                description="サポート"
            ),
        ]

        super().__init__(
            placeholder="ポジションを複数選択してください",
            min_values=1,
            max_values=5,
            options=options,
            custom_id="nexus:v52:registration:positions"
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        selected_positions = list(
            self.values
        )

        await interaction.response.send_modal(
            RegistrationModal(
                self.rank_key,
                selected_positions
            )
        )


class PositionSelectView(
    discord.ui.View
):

    def __init__(
        self,
        rank_key: str
    ):

        super().__init__(timeout=180)

        self.add_item(
            PositionSelect(rank_key)
        )


# =========================================================
# ランク選択メニュー
# =========================================================

class RankSelect(
    discord.ui.Select
):

    def __init__(self):

        options = []

        for rank_key, rank_label in RANKS:

            points = RANK_POINTS[rank_key]

            options.append(
                discord.SelectOption(
                    label=rank_label,
                    value=rank_key,
                    description=f"{points} pt"
                )
            )

        super().__init__(
            placeholder="ランクを1つ選択してください",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="nexus:v52:registration:rank"
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        rank_key = self.values[0]

        rank_label = dict(RANKS).get(
            rank_key,
            rank_key
        )

        view = PositionSelectView(
            rank_key
        )

        await interaction.response.send_message(
            f"ランクは **{rank_label}** ですね。\n"
            "次に、ポジションを1つ以上選択してください。",
            view=view,
            ephemeral=True
        )


class RankSelectView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(timeout=180)

        self.add_item(
            RankSelect()
        )


# =========================================================
# プレイヤー登録パネル
# =========================================================

class RegistrationPanelView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(
        label="プレイヤー登録",
        style=discord.ButtonStyle.primary,
        emoji="📝",
        custom_id="nexus:v52:registration:start"
    )
    async def register(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            "最初に現在のランクを1つ選択してください。",
            view=RankSelectView(),
            ephemeral=True
        )


# =========================================================
# プレイヤー登録パネルのEmbed
# =========================================================

def build_registration_panel_embed() -> discord.Embed:

    embed = discord.Embed(
        title="Nexus League プレイヤー登録",
        description=(
            "プレイヤー登録を行う場合は、"
            "下のボタンを押してください。\n\n"
            "登録は次の順番で進みます。\n"
            "① ランクを選択\n"
            "② ポジションを複数選択\n"
            "③ Riot ID・自己紹介・OP.GGを入力\n\n"
            "登録完了後、Discordのサーバー表示名が"
            "自動的に変更されます。"
        ),
        color=discord.Color.blue()
    )

    embed.add_field(
        name="表示名の形式",
        value="Riot IDの名前 / ポジション / ランク",
        inline=False
    )

    embed.add_field(
        name="登録情報の取り扱い",
        value=(
            "登録内容は指定の登録チャンネルに投稿されます。"
            "Riot IDなどの登録情報はBotのSQLiteデータベースには保存しません。"
        ),
        inline=False
    )

    return embed


# =========================================================
# 登録パネル設置処理
# =========================================================

async def send_registration_panel(
    channel: discord.TextChannel
):

    return await channel.send(
        embed=build_registration_panel_embed(),
        view=RegistrationPanelView()
    )


# =========================================================
# Part 4
# FAカード・ロールパネル・チーム結成・チーム解散・マッチング希望
# =========================================================


# =========================================================
# ロールID設定
# Renderの環境変数から取得
# =========================================================

ROLE_NORMAL_ID = int(
    os.getenv("ROLE_NORMAL_ID", "0")
) or None

ROLE_RANK_ID = int(
    os.getenv("ROLE_RANK_ID", "0")
) or None

ROLE_CUSTOM_ID = int(
    os.getenv("ROLE_CUSTOM_ID", "0")
) or None

ROLE_TOURNAMENT_ID = int(
    os.getenv("ROLE_TOURNAMENT_ID", "0")
) or None


ROLE_PANEL_CONFIG = [
    {
        "name": "ノーマル",
        "id": ROLE_NORMAL_ID,
        "emoji": "🎮",
        "custom_id": "nexus:v52:role:normal",
    },
    {
        "name": "ランク",
        "id": ROLE_RANK_ID,
        "emoji": "🏆",
        "custom_id": "nexus:v52:role:rank",
    },
    {
        "name": "カスタム",
        "id": ROLE_CUSTOM_ID,
        "emoji": "👥",
        "custom_id": "nexus:v52:role:custom",
    },
    {
        "name": "大会",
        "id": ROLE_TOURNAMENT_ID,
        "emoji": "🥇",
        "custom_id": "nexus:v52:role:tournament",
    },
]


# =========================================================
# FAカード入力モーダル
# =========================================================

class FaModal(
    discord.ui.Modal,
    title="FAカード登録"
):

    rank = discord.ui.TextInput(
        label="ランク",
        placeholder="例：Diamond I",
        max_length=50,
        required=True
    )

    position = discord.ui.TextInput(
        label="希望ポジション",
        placeholder="例：MID / ADC",
        max_length=100,
        required=True
    )

    introduction = discord.ui.TextInput(
        label="自己紹介・希望条件",
        placeholder="活動時間や希望条件など",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )

    opgg = discord.ui.TextInput(
        label="OP.GGアドレス",
        placeholder="https://www.op.gg/...",
        max_length=300,
        required=False
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            return await safe_ephemeral(
                interaction,
                "サーバー内で操作してください。"
            )

        channel = await get_text_channel(
            interaction.guild,
            REGISTRATION_CHANNEL_ID
        )

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            return await safe_ephemeral(
                interaction,
                "登録チャンネルが見つかりません。"
            )

        rank_text = normalize_input(
            self.rank.value
        )

        position_text = normalize_input(
            self.position.value
        )

        introduction_text = normalize_input(
            self.introduction.value
        )

        opgg_text = normalize_input(
            self.opgg.value
        )

        embed = discord.Embed(
            title="FAカード",
            description=(
                f"**{interaction.user.display_name}** さんが"
                "FA情報を登録しました。"
            ),
            color=discord.Color.orange(),
            timestamp=now_jst()
        )

        embed.add_field(
            name="ランク",
            value=rank_text,
            inline=True
        )

        embed.add_field(
            name="希望ポジション",
            value=position_text,
            inline=True
        )

        embed.add_field(
            name="自己紹介・希望条件",
            value=introduction_text[:1024],
            inline=False
        )

        if opgg_text:

            if re.match(
                r"^https?://",
                opgg_text,
                flags=re.IGNORECASE
            ):

                embed.add_field(
                    name="OP.GG",
                    value=f"[OP.GGを開く]({opgg_text})",
                    inline=False
                )

            else:

                embed.add_field(
                    name="OP.GG",
                    value=opgg_text[:1024],
                    inline=False
                )

        embed.set_footer(
            text=f"登録者ID：{interaction.user.id}"
        )

        try:

            await channel.send(
                embed=embed
            )

        except discord.HTTPException:

            LOG.exception(
                "FA card send failed"
            )

            return await safe_ephemeral(
                interaction,
                "FAカードの送信に失敗しました。"
            )

        log_action(
            interaction.guild.id,
            interaction.user.id,
            "fa_card_create",
            "FAカードを投稿"
        )

        await safe_ephemeral(
            interaction,
            "FAカードを登録しました。"
        )


# =========================================================
# FAカードパネル
# =========================================================

class FaPanelView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(
        label="FAカードを登録する",
        style=discord.ButtonStyle.primary,
        emoji="📝",
        custom_id="nexus:v52:fa:register"
    )
    async def register(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            FaModal()
        )


def build_fa_panel_embed() -> discord.Embed:

    return discord.Embed(
        title="FAカード登録",
        description=(
            "チームを探している方は、"
            "下のボタンからFAカードを登録してください。\n\n"
            "ランク・希望ポジション・自己紹介などを"
            "登録チャンネルに投稿します。"
        ),
        color=discord.Color.orange()
    )


# =========================================================
# ロールパネル共通処理
# =========================================================

async def toggle_role(
    interaction: discord.Interaction,
    role_name: str,
    role_id: Optional[int]
):

    if not interaction.guild:

        return await safe_ephemeral(
            interaction,
            "サーバー内で操作してください。"
        )

    if not role_id:

        return await safe_ephemeral(
            interaction,
            f"「{role_name}」ロールのIDが設定されていません。"
        )

    role = interaction.guild.get_role(
        role_id
    )

    if role is None:

        return await safe_ephemeral(
            interaction,
            f"「{role_name}」ロールが見つかりません。"
        )

    member = interaction.user

    if not isinstance(member, discord.Member):

        return await safe_ephemeral(
            interaction,
            "メンバー情報を取得できませんでした。"
        )

    try:

        if role in member.roles:

            await member.remove_roles(
                role,
                reason="ロールパネルから解除"
            )

            await safe_ephemeral(
                interaction,
                f"「{role_name}」ロールを解除しました。"
            )

        else:

            await member.add_roles(
                role,
                reason="ロールパネルから付与"
            )

            await safe_ephemeral(
                interaction,
                f"「{role_name}」ロールを付与しました。"
            )

    except discord.Forbidden:

        await safe_ephemeral(
            interaction,
            "ロールを変更できません。Botの権限とロールの位置を確認してください。"
        )

    except discord.HTTPException:

        LOG.exception(
            "Role toggle failed"
        )

        await safe_ephemeral(
            interaction,
            "ロールの変更に失敗しました。"
        )


# =========================================================
# ロールパネルView
# =========================================================

class RolePanelView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(timeout=None)

        for config in ROLE_PANEL_CONFIG:

            self.add_item(
                RoleToggleButton(config)
            )


class RoleToggleButton(
    discord.ui.Button
):

    def __init__(
        self,
        config: dict
    ):

        self.role_name = config["name"]
        self.role_id = config["id"]

        super().__init__(
            label=config["name"],
            emoji=config["emoji"],
            style=discord.ButtonStyle.primary,
            custom_id=config["custom_id"]
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        await toggle_role(
            interaction,
            self.role_name,
            self.role_id
        )


def build_role_panel_embed() -> discord.Embed:

    embed = discord.Embed(
        title="ロール選択",
        description=(
            "希望するロールのボタンを押してください。\n\n"
            "すでに所持しているロールを押すと解除されます。"
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🎮 ノーマル",
        value="ノーマル募集に関するロール",
        inline=True
    )

    embed.add_field(
        name="🏆 ランク",
        value="ランク募集に関するロール",
        inline=True
    )

    embed.add_field(
        name="👥 カスタム",
        value="カスタム募集に関するロール",
        inline=True
    )

    embed.add_field(
        name="🥇 大会",
        value="大会に関するロール",
        inline=True
    )

    return embed


# =========================================================
# チーム結成モーダル
# 入力項目はチーム名のみ
# =========================================================

class TeamCreateModal(
    discord.ui.Modal,
    title="チーム結成"
):

    team_name = discord.ui.TextInput(
        label="チーム名",
        placeholder="チーム名を入力してください",
        max_length=80,
        required=True
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            return await safe_ephemeral(
                interaction,
                "サーバー内で操作してください。"
            )

        guild = interaction.guild

        category = None

        if TEAM_CATEGORY_ID:

            category = guild.get_channel(
                TEAM_CATEGORY_ID
            )

            if not isinstance(
                category,
                discord.CategoryChannel
            ):

                category = None

        team_name_value = normalize_input(
            self.team_name.value
        )

        if not team_name_value:

            return await safe_ephemeral(
                interaction,
                "チーム名を入力してください。"
            )

        bot_member = guild.me

        if bot_member is None:

            return await safe_ephemeral(
                interaction,
                "Botのメンバー情報を取得できませんでした。"
            )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True
            )
        }

        # 運営ロールにも閲覧権限を付与
        if OPERATIONS_ROLE_ID:

            operations_role = guild.get_role(
                OPERATIONS_ROLE_ID
            )

            if operations_role:

                overwrites[operations_role] = (
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    )
                )

        try:

            # チャンネル名は指定どおり固定
            channel = await guild.create_text_channel(
                name="チーム結成",
                category=category,
                overwrites=overwrites,
                topic=(
                    f"チーム名：{team_name_value} / "
                    f"作成者：{interaction.user.id}"
                ),
                reason="チーム結成受付"
            )

            await channel.send(
                f"{interaction.user.mention} さん、"
                "チーム結成用チャンネルを作成しました。\n\n"
                f"**チーム名：{discord.utils.escape_markdown(team_name_value)}**\n\n"
                "メンバー構成・募集条件・活動時間など、"
                "必要な情報をこのチャンネルで入力してください。",
                allowed_mentions=discord.AllowedMentions(
                    users=True
                )
            )

        except discord.Forbidden:

            return await safe_ephemeral(
                interaction,
                "チャンネルを作成できません。Botにチャンネル管理権限があるか確認してください。"
            )

        except discord.HTTPException:

            LOG.exception(
                "Team channel creation failed"
            )

            return await safe_ephemeral(
                interaction,
                "チーム結成チャンネルの作成に失敗しました。"
            )

        log_action(
            guild.id,
            interaction.user.id,
            "team_create_request",
            f"チーム名：{team_name_value}"
        )

        await safe_ephemeral(
            interaction,
            f"チーム結成チャンネルを作成しました：{channel.mention}"
        )


# =========================================================
# チーム解散モーダル
# =========================================================

class TeamDisbandModal(
    discord.ui.Modal,
    title="チーム解散申請"
):

    team_name = discord.ui.TextInput(
        label="チーム名",
        placeholder="解散するチーム名",
        max_length=80,
        required=True
    )

    reason = discord.ui.TextInput(
        label="解散理由",
        placeholder="解散理由を入力してください",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            return await safe_ephemeral(
                interaction,
                "サーバー内で操作してください。"
            )

        guild = interaction.guild

        category = None

        if TEAM_CATEGORY_ID:

            candidate = guild.get_channel(
                TEAM_CATEGORY_ID
            )

            if isinstance(
                candidate,
                discord.CategoryChannel
            ):

                category = candidate

        bot_member = guild.me

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
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

            if operations_role:

                overwrites[operations_role] = (
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    )
                )

        team_name_value = normalize_input(
            self.team_name.value
        )

        reason_value = normalize_input(
            self.reason.value
        ) or "未記入"

        try:

            channel = await guild.create_text_channel(
                name="チーム解散",
                category=category,
                overwrites=overwrites,
                topic=(
                    f"解散申請：{team_name_value} / "
                    f"申請者：{interaction.user.id}"
                ),
                reason="チーム解散申請"
            )

            await channel.send(
                f"{interaction.user.mention} さんのチーム解散申請です。\n\n"
                f"**チーム名：{discord.utils.escape_markdown(team_name_value)}**\n"
                f"**解散理由：**\n{reason_value}\n\n"
                "運営と確認を進めてください。",
                allowed_mentions=discord.AllowedMentions(
                    users=True
                )
            )

        except discord.Forbidden:

            return await safe_ephemeral(
                interaction,
                "チーム解散チャンネルを作成できません。Botの権限を確認してください。"
            )

        except discord.HTTPException:

            LOG.exception(
                "Team disband channel creation failed"
            )

            return await safe_ephemeral(
                interaction,
                "チーム解散チャンネルの作成に失敗しました。"
            )

        log_action(
            guild.id,
            interaction.user.id,
            "team_disband_request",
            f"チーム名：{team_name_value} / 理由：{reason_value}"
        )

        await safe_ephemeral(
            interaction,
            f"チーム解散申請チャンネルを作成しました：{channel.mention}"
        )


# =========================================================
# マッチング希望チャンネル作成
# ボタンを押したら即時作成
# =========================================================

async def create_matching_channel(
    interaction: discord.Interaction
):

    if not interaction.guild:

        return await safe_ephemeral(
            interaction,
            "サーバー内で操作してください。"
        )

    guild = interaction.guild

    category = None

    if MATCHING_CATEGORY_ID:

        candidate = guild.get_channel(
            MATCHING_CATEGORY_ID
        )

        if isinstance(
            candidate,
            discord.CategoryChannel
        ):

            category = candidate

    bot_member = guild.me

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False
        ),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True
        ),
        bot_member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True
        )
    }

    if OPERATIONS_ROLE_ID:

        operations_role = guild.get_role(
            OPERATIONS_ROLE_ID
        )

        if operations_role:

            overwrites[operations_role] = (
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
            )

    try:

        # 事前入力なしでチャンネルを作成
        channel = await guild.create_text_channel(
            name="マッチング希望",
            category=category,
            overwrites=overwrites,
            topic=f"申請者：{interaction.user.id}",
            reason="マッチング希望受付"
        )

        await channel.send(
            f"{interaction.user.mention} さん、"
            "マッチング希望チャンネルを作成しました。\n\n"
            "希望するゲームモード・ランク・ポジション・"
            "活動時間などを、この部屋で入力してください。",
            allowed_mentions=discord.AllowedMentions(
                users=True
            )
        )

    except discord.Forbidden:

        return await safe_ephemeral(
            interaction,
            "マッチング希望チャンネルを作成できません。Botの権限を確認してください。"
        )

    except discord.HTTPException:

        LOG.exception(
            "Matching channel creation failed"
        )

        return await safe_ephemeral(
            interaction,
            "マッチング希望チャンネルの作成に失敗しました。"
        )

    log_action(
        guild.id,
        interaction.user.id,
        "matching_request",
        "マッチング希望チャンネルを作成"
    )

    await safe_ephemeral(
        interaction,
        f"マッチング希望チャンネルを作成しました：{channel.mention}"
    )


# =========================================================
# チーム・マッチングパネル
# =========================================================

class PrivateRequestModal(
    discord.ui.Modal,
    title="チーム結成"
):

    team_name = discord.ui.TextInput(
        label="チーム名",
        placeholder="チーム名を入力してください",
        max_length=80,
        required=True
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        # チーム名だけでチャンネルを作成
        modal = TeamCreateModal.__new__(
            TeamCreateModal
        )

        await create_team_channel_from_name(
            interaction,
            normalize_input(self.team_name.value)
        )


async def create_team_channel_from_name(
    interaction: discord.Interaction,
    team_name_value: str
):

    if not interaction.guild:

        return await safe_ephemeral(
            interaction,
            "サーバー内で操作してください。"
        )

    guild = interaction.guild

    category = None

    if TEAM_CATEGORY_ID:

        candidate = guild.get_channel(
            TEAM_CATEGORY_ID
        )

        if isinstance(
            candidate,
            discord.CategoryChannel
        ):

            category = candidate

    bot_member = guild.me

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False
        ),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True
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

        if operations_role:

            overwrites[operations_role] = (
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
            )

    try:

        channel = await guild.create_text_channel(
            name="チーム結成",
            category=category,
            overwrites=overwrites,
            topic=(
                f"チーム名：{team_name_value} / "
                f"作成者：{interaction.user.id}"
            ),
            reason="チーム結成受付"
        )

        await channel.send(
            f"{interaction.user.mention} さん、"
            "チーム結成用チャンネルを作成しました。\n\n"
            f"**チーム名：{discord.utils.escape_markdown(team_name_value)}**\n\n"
            "その他の情報は、この部屋で入力してください。",
            allowed_mentions=discord.AllowedMentions(
                users=True
            )
        )

    except discord.Forbidden:

        return await safe_ephemeral(
            interaction,
            "チーム結成チャンネルを作成できません。Botの権限を確認してください。"
        )

    except discord.HTTPException:

        LOG.exception(
            "Team channel creation failed"
        )

        return await safe_ephemeral(
            interaction,
            "チーム結成チャンネルの作成に失敗しました。"
        )

    log_action(
        guild.id,
        interaction.user.id,
        "team_create_request",
        f"チーム名：{team_name_value}"
    )

    await safe_ephemeral(
        interaction,
        f"チーム結成チャンネルを作成しました：{channel.mention}"
    )


class RequestPanelView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(
        label="チーム結成",
        style=discord.ButtonStyle.success,
        emoji="🛡️",
        custom_id="nexus:v52:request:team_create"
    )
    async def team_create(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            TeamCreateModal()
        )

    @discord.ui.button(
        label="チーム解散",
        style=discord.ButtonStyle.danger,
        emoji="🗑️",
        custom_id="nexus:v52:request:team_disband"
    )
    async def team_disband(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            TeamDisbandModal()
        )

    @discord.ui.button(
        label="マッチング希望",
        style=discord.ButtonStyle.primary,
        emoji="🔎",
        custom_id="nexus:v52:request:matching"
    )
    async def matching(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await create_matching_channel(
            interaction
        )


def build_request_panel_embed() -> discord.Embed:

    embed = discord.Embed(
        title="チーム・マッチング受付",
        description=(
            "希望する項目のボタンを押してください。\n\n"
            "🛡️ **チーム結成**\n"
            "チーム名を入力すると専用チャンネルを作成します。\n\n"
            "🗑️ **チーム解散**\n"
            "チーム名と解散理由を入力して申請します。\n\n"
            "🔎 **マッチング希望**\n"
            "ボタンを押すと専用チャンネルをすぐに作成します。"
        ),
        color=discord.Color.blurple()
    )

    return embed


# =========================================================
# Part 5
# 大会作成・大会参加・辞退・チーム名照合・締切表示
# =========================================================


# =========================================================
# 大会情報取得
# =========================================================

def get_tournament(
    tournament_id: int
):

    with connect() as con:

        return con.execute("""
            SELECT *
            FROM tournaments
            WHERE id=?
        """, (
            tournament_id,
        )).fetchone()


def get_tournament_entries(
    tournament_id: int
):

    with connect() as con:

        return con.execute("""
            SELECT
                user_id,
                team_name,
                members,
                created_at
            FROM tournament_entries
            WHERE tournament_id=?
            ORDER BY created_at ASC
        """, (
            tournament_id,
        )).fetchall()


# =========================================================
# 大会参加者一覧Embed
# =========================================================

def build_tournament_embed(
    tournament_id: int
) -> Optional[discord.Embed]:

    tournament = get_tournament(
        tournament_id
    )

    if tournament is None:
        return None

    entries = get_tournament_entries(
        tournament_id
    )

    embed = discord.Embed(
        title=tournament["name"],
        description=(
            f"## {tournament['starts_display'] or tournament['starts_at']}\n"
            f"## 開催時間：{tournament['rules'][:0] if False else ''}"
        ),
        color=discord.Color.gold()
    )

    # 開催日時・締切日時は入力された表示文字列を使う
    # ISO形式のタイムゾーン表記は画面に出さない
    embed.description = (
        f"## 開催日：{tournament['starts_display'] or '未設定'}\n"
        f"## 参加締切：{tournament['deadline_display'] or '未設定'}"
    )

    embed.add_field(
        name="大会ルール",
        value=tournament["rules"][:1024] or "未設定",
        inline=False
    )

    if entries:

        lines = []

        for index, entry in enumerate(
            entries,
            start=1
        ):

            team_name = discord.utils.escape_markdown(
                entry["team_name"]
            )

            lines.append(
                f"**{index}. {team_name}**"
            )

        participant_text = "\n".join(lines)

    else:

        participant_text = "まだ参加チームはありません。"

    embed.add_field(
        name=f"参加チーム（{len(entries)}チーム）",
        value=participant_text[:1024],
        inline=False
    )

    embed.set_footer(
        text=f"大会ID：{tournament_id}"
    )

    return embed


# =========================================================
# 大会参加・辞退時の一覧更新
# =========================================================

async def refresh_tournament_message(
    bot: commands.Bot,
    tournament_id: int
):

    tournament = get_tournament(
        tournament_id
    )

    if tournament is None:
        return

    if not tournament["channel_id"] or not tournament["message_id"]:
        return

    channel = bot.get_channel(
        tournament["channel_id"]
    )

    if channel is None:

        try:

            channel = await bot.fetch_channel(
                tournament["channel_id"]
            )

        except discord.HTTPException:

            return

    try:

        message = await channel.fetch_message(
            tournament["message_id"]
        )

        embed = build_tournament_embed(
            tournament_id
        )

        if embed is not None:

            await message.edit(
                embed=embed,
                view=TournamentPanelView(
                    tournament_id
                )
            )

    except discord.HTTPException:

        LOG.exception(
            "Tournament message refresh failed"
        )


# =========================================================
# 大会参加・辞退モーダル
# =========================================================

class TournamentEntryModal(
    discord.ui.Modal
):

    team_name = discord.ui.TextInput(
        label="チーム名",
        placeholder="登録するチーム名を入力してください",
        max_length=80,
        required=True
    )

    def __init__(
        self,
        tournament_id: int,
        action: str
    ):

        self.tournament_id = tournament_id
        self.action = action

        if action == "join":

            title = "大会に参加する"

        else:

            title = "大会を辞退する"

        super().__init__(
            title=title
        )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        team_name_value = normalize_input(
            self.team_name.value
        )

        if not team_name_value:

            return await safe_ephemeral(
                interaction,
                "チーム名を入力してください。"
            )

        tournament = get_tournament(
            self.tournament_id
        )

        if tournament is None:

            return await safe_ephemeral(
                interaction,
                "大会が見つかりません。"
            )

        if tournament["status"] != "open":

            return await safe_ephemeral(
                interaction,
                "この大会は現在受付を終了しています。"
            )

        # 締切確認
        if tournament["deadline"]:

            try:

                deadline = datetime.fromisoformat(
                    tournament["deadline"]
                )

                if deadline.tzinfo is None:

                    deadline = deadline.replace(
                        tzinfo=JST
                    )

                if now_jst() > deadline.astimezone(JST):

                    return await safe_ephemeral(
                        interaction,
                        "参加締切を過ぎています。"
                    )

            except ValueError:

                LOG.warning(
                    "Invalid tournament deadline: %s",
                    tournament["deadline"]
                )

        user_id = interaction.user.id

        if self.action == "join":

            # 既に参加している場合は二重登録しない
            with connect() as con:

                existing = con.execute("""
                    SELECT id, team_name
                    FROM tournament_entries
                    WHERE tournament_id=?
                    AND user_id=?
                """, (
                    self.tournament_id,
                    user_id
                )).fetchone()

                if existing:

                    return await safe_ephemeral(
                        interaction,
                        "すでにこの大会へ参加登録されています。"
                    )

                con.execute("""
                    INSERT INTO tournament_entries (
                        tournament_id,
                        user_id,
                        team_name,
                        members,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    self.tournament_id,
                    user_id,
                    team_name_value,
                    "",
                    now_iso()
                ))

            log_action(
                interaction.guild.id if interaction.guild else None,
                user_id,
                "tournament_join",
                f"大会ID：{self.tournament_id} / チーム名：{team_name_value}"
            )

            await refresh_tournament_message(
                interaction.client,
                self.tournament_id
            )

            return await safe_ephemeral(
                interaction,
                f"「{team_name_value}」で大会参加登録しました。"
            )

        # =================================================
        # 辞退処理
        # 登録時と入力チーム名が完全一致した場合のみ削除
        # =================================================

        with connect() as con:

            existing = con.execute("""
                SELECT id, team_name
                FROM tournament_entries
                WHERE tournament_id=?
                AND user_id=?
            """, (
                self.tournament_id,
                user_id
            )).fetchone()

            if existing is None:

                return await safe_ephemeral(
                    interaction,
                    "この大会への参加登録が見つかりません。"
                )

            if existing["team_name"] != team_name_value:

                return await safe_ephemeral(
                    interaction,
                    "入力されたチーム名が参加登録時の名前と一致しません。\n"
                    "登録したチーム名をそのまま入力してください。"
                )

            con.execute("""
                DELETE FROM tournament_entries
                WHERE tournament_id=?
                AND user_id=?
                AND team_name=?
            """, (
                self.tournament_id,
                user_id,
                team_name_value
            ))

        log_action(
            interaction.guild.id if interaction.guild else None,
            user_id,
            "tournament_withdraw",
            f"大会ID：{self.tournament_id} / チーム名：{team_name_value}"
        )

        await refresh_tournament_message(
            interaction.client,
            self.tournament_id
        )

        await safe_ephemeral(
            interaction,
            f"「{team_name_value}」の大会参加を辞退しました。"
        )


# =========================================================
# 大会参加パネル
# =========================================================

class TournamentPanelView(
    discord.ui.View
):

    def __init__(
        self,
        tournament_id: int
    ):

        super().__init__(timeout=None)

        self.tournament_id = tournament_id

        self.add_item(
            TournamentJoinButton(
                tournament_id
            )
        )

        self.add_item(
            TournamentWithdrawButton(
                tournament_id
            )
        )


class TournamentJoinButton(
    discord.ui.Button
):

    def __init__(
        self,
        tournament_id: int
    ):

        super().__init__(
            label="大会に参加する",
            style=discord.ButtonStyle.success,
            emoji="🏆",
            custom_id=f"nexus:v52:tournament:join:{tournament_id}"
        )

        self.tournament_id = tournament_id

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        await interaction.response.send_modal(
            TournamentEntryModal(
                self.tournament_id,
                "join"
            )
        )


class TournamentWithdrawButton(
    discord.ui.Button
):

    def __init__(
        self,
        tournament_id: int
    ):

        super().__init__(
            label="辞退する",
            style=discord.ButtonStyle.danger,
            emoji="🚪",
            custom_id=f"nexus:v52:tournament:withdraw:{tournament_id}"
        )

        self.tournament_id = tournament_id

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        await interaction.response.send_modal(
            TournamentEntryModal(
                self.tournament_id,
                "withdraw"
            )
        )


# =========================================================
# 大会作成モーダル
# =========================================================

class TournamentCreateModal(
    discord.ui.Modal,
    title="大会を作成"
):

    name = discord.ui.TextInput(
        label="大会名",
        placeholder="大会名を入力してください",
        max_length=100,
        required=True
    )

    starts_date = discord.ui.TextInput(
        label="開催日（月日）",
        placeholder="例：11月22日",
        max_length=20,
        required=True
    )

    starts_time = discord.ui.TextInput(
        label="開催時間",
        placeholder="例：21:00",
        max_length=10,
        required=True
    )

    deadline_date = discord.ui.TextInput(
        label="参加締切日（月日）",
        placeholder="例：11月20日",
        max_length=20,
        required=True
    )

    deadline_time = discord.ui.TextInput(
        label="参加締切時間",
        placeholder="例：23:00",
        max_length=10,
        required=True
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            return await safe_ephemeral(
                interaction,
                "サーバー内で操作してください。"
            )

        tournament_name = normalize_input(
            self.name.value
        )

        try:

            starts_at, starts_date_display, starts_time_display = (
                parse_custom_date(
                    self.starts_date.value,
                    self.starts_time.value
                )
            )

            deadline_at, deadline_date_display, deadline_time_display = (
                parse_custom_date(
                    self.deadline_date.value,
                    self.deadline_time.value
                )
            )

        except ValueError as error:

            return await safe_ephemeral(
                interaction,
                str(error)
            )

        if deadline_at >= starts_at:

            return await safe_ephemeral(
                interaction,
                "参加締切は大会開催日時より前に設定してください。"
            )

        channel = await get_text_channel(
            interaction.guild,
            TOURNAMENT_CHANNEL_ID
        )

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            return await safe_ephemeral(
                interaction,
                "大会投稿チャンネルが見つかりません。"
            )

        # 大会情報をDBに登録
        with connect() as con:

            cursor = con.execute("""
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
                    deadline,
                    starts_display,
                    deadline_display
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                interaction.guild.id,
                interaction.user.id,
                tournament_name,
                starts_at.isoformat(),
                "チーム参加のみ",
                "team",
                "open",
                channel.id,
                None,
                now_iso(),
                deadline_at.isoformat(),
                f"{starts_date_display} {starts_time_display}",
                f"{deadline_date_display} {deadline_time_display}"
            ))

            tournament_id = cursor.lastrowid

        embed = build_tournament_embed(
            tournament_id
        )

        if embed is None:

            return await safe_ephemeral(
                interaction,
                "大会情報の作成に失敗しました。"
            )

        try:

            message = await channel.send(
                embed=embed,
                view=TournamentPanelView(
                    tournament_id
                )
            )

        except discord.HTTPException:

            LOG.exception(
                "Tournament post failed"
            )

            with connect() as con:

                con.execute("""
                    UPDATE tournaments
                    SET status='error'
                    WHERE id=?
                """, (
                    tournament_id,
                ))

            return await safe_ephemeral(
                interaction,
                "大会の投稿に失敗しました。"
            )

        with connect() as con:

            con.execute("""
                UPDATE tournaments
                SET message_id=?
                WHERE id=?
            """, (
                message.id,
                tournament_id
            ))

        log_action(
            interaction.guild.id,
            interaction.user.id,
            "tournament_create",
            f"大会ID：{tournament_id} / 大会名：{tournament_name}"
        )

        await safe_ephemeral(
            interaction,
            f"大会を投稿しました：{message.jump_url}"
        )


# =========================================================
# 大会作成パネル
# =========================================================

class TournamentCreatePanelView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(
        label="大会を作成する",
        style=discord.ButtonStyle.primary,
        emoji="🏆",
        custom_id="nexus:v52:tournament:create"
    )
    async def create(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not interaction.user.guild_permissions.administrator:

            return await safe_ephemeral(
                interaction,
                "大会作成は管理者のみ実行できます。"
            )

        await interaction.response.send_modal(
            TournamentCreateModal()
        )


def build_tournament_create_embed() -> discord.Embed:

    return discord.Embed(
        title="大会作成パネル",
        description=(
            "管理者は下のボタンから大会を作成できます。\n\n"
            "開催日・開催時間・参加締切を設定できます。\n"
            "参加形式はチーム参加のみです。"
        ),
        color=discord.Color.gold()
    )


# =========================================================
# 大会パネル再登録
# Bot再起動後も過去の大会ボタンを動作させる
# =========================================================

def register_tournament_views(
    bot: commands.Bot
):

    with connect() as con:

        rows = con.execute("""
            SELECT id
            FROM tournaments
            WHERE status='open'
            AND message_id IS NOT NULL
        """).fetchall()

    for row in rows:

        tournament_id = row["id"]

        bot.add_view(
            TournamentPanelView(
                tournament_id
            )
        )


# =========================================================
# Part 6
# Bot本体・起動処理・スラッシュコマンド・活動記録・Render対応
# =========================================================


# =========================================================
# 活動記録用テーブル
# 登録情報・Riot IDは保存しない
# =========================================================

def init_activity_tables():

    with connect() as con:

        con.execute("""
            CREATE TABLE IF NOT EXISTS nexus_voice_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                joined_at TEXT NOT NULL,
                left_at TEXT,
                duration_seconds INTEGER DEFAULT 0
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS nexus_message_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)


# =========================================================
# 活動レポート作成
# =========================================================

def build_activity_report(
    guild_id: int,
    days: int = 1
) -> str:

    start = now_jst() - timedelta(
        days=days
    )

    start_text = start.isoformat()

    with connect() as con:

        voice_rows = con.execute("""
            SELECT
                user_id,
                SUM(duration_seconds) AS total_seconds
            FROM nexus_voice_activity
            WHERE guild_id=?
            AND joined_at>=?
            GROUP BY user_id
            ORDER BY total_seconds DESC
            LIMIT 20
        """, (
            guild_id,
            start_text
        )).fetchall()

        message_rows = con.execute("""
            SELECT
                user_id,
                COUNT(*) AS total_messages
            FROM nexus_message_activity
            WHERE guild_id=?
            AND created_at>=?
            GROUP BY user_id
            ORDER BY total_messages DESC
            LIMIT 20
        """, (
            guild_id,
            start_text
        )).fetchall()

    lines = []

    lines.append(
        f"活動期間：過去{days}日間"
    )

    lines.append("")
    lines.append("【VC活動ランキング】")

    if voice_rows:

        for index, row in enumerate(
            voice_rows,
            start=1
        ):

            minutes = int(
                row["total_seconds"] or 0
            ) // 60

            hours = minutes // 60
            remaining_minutes = minutes % 60

            lines.append(
                f"{index}. <@{row['user_id']}> "
                f"{hours}時間{remaining_minutes}分"
            )

    else:

        lines.append(
            "VC活動記録はありません。"
        )

    lines.append("")
    lines.append("【メッセージ投稿ランキング】")

    if message_rows:

        for index, row in enumerate(
            message_rows,
            start=1
        ):

            lines.append(
                f"{index}. <@{row['user_id']}> "
                f"{row['total_messages']}件"
            )

    else:

        lines.append(
            "メッセージ投稿記録はありません。"
        )

    return "\n".join(lines)


# =========================================================
# Botステータス表示
# =========================================================

def build_bot_status_embed(
    bot: commands.Bot
) -> discord.Embed:

    embed = discord.Embed(
        title="Nexus League Bot 状態",
        color=discord.Color.green()
    )

    embed.add_field(
        name="接続状態",
        value="オンライン",
        inline=True
    )

    embed.add_field(
        name="Ping",
        value=f"{round(bot.latency * 1000)}ms",
        inline=True
    )

    embed.add_field(
        name="サーバー数",
        value=str(len(bot.guilds)),
        inline=True
    )

    embed.add_field(
        name="Botユーザー",
        value=str(bot.user),
        inline=False
    )

    embed.add_field(
        name="Python",
        value="Python 3.10以上",
        inline=True
    )

    embed.add_field(
        name="DB",
        value="SQLite",
        inline=True
    )

    embed.timestamp = now_jst()

    return embed


# =========================================================
# 管理パネルEmbed
# =========================================================

def build_admin_panel_embed() -> discord.Embed:

    return discord.Embed(
        title="Nexus League Bot 管理パネル",
        description=(
            "管理者向けの操作一覧です。\n\n"
            "・`/setup` パネル一括設置\n"
            "・`/fa_card` FAカード作成\n"
            "・`/tournament` 大会作成\n"
            "・`/daily_report` 活動レポート\n"
            "・`/activity_stats` 活動集計\n"
            "・`/bot_status` Bot状態確認\n"
            "・`/operation_logs` 操作ログ確認"
        ),
        color=discord.Color.dark_blue()
    )


# =========================================================
# Nexus Bot本体
# =========================================================

class NexusBot(commands.Bot):

    def __init__(self):

        intents = discord.Intents.default()

        intents.guilds = True
        intents.members = True
        intents.message_content = True
        intents.voice_states = True

        super().__init__(
            command_prefix="!",
            intents=intents
        )

        self.web_runner = None

    # -----------------------------------------------------
    # 起動時処理
    # -----------------------------------------------------

    async def setup_hook(self):

        init_db()
        init_activity_tables()

        # 永続View登録
        self.add_view(
            RecruitmentView()
        )

        self.add_view(
            CustomRecruitmentPanelView()
        )

        self.add_view(
            RegistrationPanelView()
        )

        self.add_view(
            FaPanelView()
        )

        self.add_view(
            RolePanelView()
        )

        self.add_view(
            RequestPanelView()
        )

        self.add_view(
            TournamentCreatePanelView()
        )

        # 過去に作成された大会のボタンも復旧
        register_tournament_views(
            self
        )

        # スラッシュコマンド同期
        if GUILD_ID:

            guild_object = discord.Object(
                id=GUILD_ID
            )

            self.tree.copy_global_to(
                guild=guild_object
            )

            await self.tree.sync(
                guild=guild_object
            )

        else:

            await self.tree.sync()

        LOG.info(
            "Nexus League Bot setup completed"
        )

        # Render用HTTPサーバー起動
        await self.start_health_server()

    # -----------------------------------------------------
    # Renderヘルスチェック
    # -----------------------------------------------------

    async def start_health_server(self):

        app = web.Application()

        async def health(request):

            return web.Response(
                text="Nexus League Bot is running.",
                status=200
            )

        app.router.add_get(
            "/",
            health
        )

        app.router.add_get(
            "/health",
            health
        )

        self.web_runner = web.AppRunner(
            app
        )

        await self.web_runner.setup()

        site = web.TCPSite(
            self.web_runner,
            "0.0.0.0",
            PORT
        )

        await site.start()

        LOG.info(
            "Health server started on port %s",
            PORT
        )

    # -----------------------------------------------------
    # 接続完了
    # -----------------------------------------------------

    async def on_ready(self):

        LOG.info(
            "Logged in as %s",
            self.user
        )

        print(
            f"ログイン成功：{self.user}"
        )

        print(
            f"接続サーバー数：{len(self.guilds)}"
        )

    # -----------------------------------------------------
    # メッセージ活動記録
    # -----------------------------------------------------

    async def on_message(
        self,
        message: discord.Message
    ):

        if message.author.bot:
            return

        if message.guild is None:
            return

        # メッセージ活動を記録
        try:

            with connect() as con:

                con.execute("""
                    INSERT INTO nexus_message_activity (
                        guild_id,
                        user_id,
                        channel_id,
                        created_at
                    )
                    VALUES (?, ?, ?, ?)
                """, (
                    message.guild.id,
                    message.author.id,
                    message.channel.id,
                    now_iso()
                ))

        except Exception:

            LOG.exception(
                "Message activity recording failed"
            )

        # 募集チャンネルの投稿を処理
        channel_kind = None

        for kind, channel_id in RECRUIT_CHANNELS.items():

            if message.channel.id == channel_id:

                channel_kind = kind
                break

        if channel_kind:

            try:

                await process_normal_recruitment(
                    message,
                    channel_kind
                )

            except Exception:

                LOG.exception(
                    "Recruitment processing failed"
                )

        await self.process_commands(
            message
        )

    # -----------------------------------------------------
    # VC参加・退出記録
    # -----------------------------------------------------

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ):

        if member.bot:
            return

        guild_id = member.guild.id
        user_id = member.id

        # VC退出
        if before.channel and (
            after.channel is None
            or before.channel.id != after.channel.id
        ):

            with connect() as con:

                active = con.execute("""
                    SELECT id, joined_at
                    FROM nexus_voice_activity
                    WHERE guild_id=?
                    AND user_id=?
                    AND left_at IS NULL
                    ORDER BY id DESC
                    LIMIT 1
                """, (
                    guild_id,
                    user_id
                )).fetchone()

                if active:

                    joined_at = datetime.fromisoformat(
                        active["joined_at"]
                    )

                    duration = max(
                        0,
                        int(
                            (
                                now_jst() - joined_at
                            ).total_seconds()
                        )
                    )

                    con.execute("""
                        UPDATE nexus_voice_activity
                        SET left_at=?,
                            duration_seconds=?
                        WHERE id=?
                    """, (
                        now_iso(),
                        duration,
                        active["id"]
                    ))

        # VC参加
        if after.channel and (
            before.channel is None
            or before.channel.id != after.channel.id
        ):

            with connect() as con:

                con.execute("""
                    INSERT INTO nexus_voice_activity (
                        guild_id,
                        user_id,
                        channel_id,
                        joined_at,
                        left_at,
                        duration_seconds
                    )
                    VALUES (?, ?, ?, ?, NULL, 0)
                """, (
                    guild_id,
                    user_id,
                    after.channel.id,
                    now_iso()
                ))


# =========================================================
# Botインスタンス
# =========================================================

bot = NexusBot()


# =========================================================
# 管理者チェック
# =========================================================

def admin_check(
    interaction: discord.Interaction
) -> bool:

    return is_admin(
        interaction
    )


# =========================================================
# /setup
# 各種パネルを設置
# =========================================================

@bot.tree.command(
    name="setup",
    description="Nexus League Botの各種パネルを設置します"
)
@app_commands.check(admin_check)
async def setup_command(
    interaction: discord.Interaction
):

    await interaction.response.defer(
        ephemeral=True
    )

    channel = interaction.channel

    if not isinstance(
        channel,
        discord.TextChannel
    ):

        return await interaction.followup.send(
            "テキストチャンネルで実行してください。",
            ephemeral=True
        )

    try:

        await channel.send(
            embed=build_registration_panel_embed(),
            view=RegistrationPanelView()
        )

        await channel.send(
            embed=build_fa_panel_embed(),
            view=FaPanelView()
        )

        await channel.send(
            embed=build_role_panel_embed(),
            view=RolePanelView()
        )

        await channel.send(
            embed=build_request_panel_embed(),
            view=RequestPanelView()
        )

        await channel.send(
            embed=build_tournament_create_embed(),
            view=TournamentCreatePanelView()
        )

        await interaction.followup.send(
            "各種パネルを設置しました。",
            ephemeral=True
        )

        log_action(
            interaction.guild.id if interaction.guild else None,
            interaction.user.id,
            "setup",
            "各種パネル設置"
        )

    except discord.HTTPException:

        LOG.exception(
            "Setup panel posting failed"
        )

        await interaction.followup.send(
            "パネル設置中にエラーが発生しました。",
            ephemeral=True
        )


# =========================================================
# /fa_card
# 実行直後にFAカード入力モーダルを表示
# 管理者限定
# =========================================================

@bot.tree.command(
    name="fa_card",
    description="FAカードを作成します"
)
@app_commands.check(admin_check)
async def fa_card_command(
    interaction: discord.Interaction
):

    await interaction.response.send_modal(
        FaModal()
    )


# =========================================================
# /tournament
# 大会作成
# =========================================================

@bot.tree.command(
    name="tournament",
    description="大会を作成します"
)
@app_commands.check(admin_check)
async def tournament_command(
    interaction: discord.Interaction
):

    await interaction.response.send_modal(
        TournamentCreateModal()
    )


# =========================================================
# /recruit_panel
# カスタム募集パネル設置
# =========================================================

@bot.tree.command(
    name="recruit_panel",
    description="カスタム募集パネルを設置します"
)
@app_commands.check(admin_check)
async def recruit_panel_command(
    interaction: discord.Interaction
):

    if not isinstance(
        interaction.channel,
        discord.TextChannel
    ):

        return await safe_ephemeral(
            interaction,
            "テキストチャンネルで実行してください。"
        )

    await interaction.channel.send(
        "カスタム募集を作成できます。",
        view=CustomRecruitmentPanelView()
    )

    await safe_ephemeral(
        interaction,
        "カスタム募集パネルを設置しました。"
    )


# =========================================================
# /role_panel
# ロールパネル設置
# =========================================================

@bot.tree.command(
    name="role_panel",
    description="ロールパネルを設置します"
)
@app_commands.check(admin_check)
async def role_panel_command(
    interaction: discord.Interaction
):

    if not isinstance(
        interaction.channel,
        discord.TextChannel
    ):

        return await safe_ephemeral(
            interaction,
            "テキストチャンネルで実行してください。"
        )

    await interaction.channel.send(
        embed=build_role_panel_embed(),
        view=RolePanelView()
    )

    await safe_ephemeral(
        interaction,
        "ロールパネルを設置しました。"
    )


# =========================================================
# /team_panel
# チーム・解散・マッチングパネル設置
# =========================================================

@bot.tree.command(
    name="team_panel",
    description="チーム関連パネルを設置します"
)
@app_commands.check(admin_check)
async def team_panel_command(
    interaction: discord.Interaction
):

    if not isinstance(
        interaction.channel,
        discord.TextChannel
    ):

        return await safe_ephemeral(
            interaction,
            "テキストチャンネルで実行してください。"
        )

    await interaction.channel.send(
        embed=build_request_panel_embed(),
        view=RequestPanelView()
    )

    await safe_ephemeral(
        interaction,
        "チーム関連パネルを設置しました。"
    )


# =========================================================
# /daily_report
# 1日分の活動レポート
# =========================================================

@bot.tree.command(
    name="daily_report",
    description="過去1日間の活動レポートを表示します"
)
@app_commands.check(admin_check)
async def daily_report_command(
    interaction: discord.Interaction
):

    if interaction.guild is None:

        return await safe_ephemeral(
            interaction,
            "サーバー内で実行してください。"
        )

    report = build_activity_report(
        interaction.guild.id,
        days=1
    )

    embed = discord.Embed(
        title="日次活動レポート",
        description=report[:4000],
        color=discord.Color.blue()
    )

    embed.timestamp = now_jst()

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# /activity_stats
# 7日間の活動集計
# =========================================================

@bot.tree.command(
    name="activity_stats",
    description="過去7日間の活動状況を表示します"
)
@app_commands.check(admin_check)
async def activity_stats_command(
    interaction: discord.Interaction
):

    if interaction.guild is None:

        return await safe_ephemeral(
            interaction,
            "サーバー内で実行してください。"
        )

    report = build_activity_report(
        interaction.guild.id,
        days=7
    )

    embed = discord.Embed(
        title="週間活動レポート",
        description=report[:4000],
        color=discord.Color.purple()
    )

    embed.timestamp = now_jst()

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# /bot_status
# Bot状態確認
# =========================================================

@bot.tree.command(
    name="bot_status",
    description="Botの稼働状況を確認します"
)
@app_commands.check(admin_check)
async def bot_status_command(
    interaction: discord.Interaction
):

    embed = build_bot_status_embed(
        bot
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# /admin_panel
# 管理パネル表示
# =========================================================

@bot.tree.command(
    name="admin_panel",
    description="管理パネルを表示します"
)
@app_commands.check(admin_check)
async def admin_panel_command(
    interaction: discord.Interaction
):

    await interaction.response.send_message(
        embed=build_admin_panel_embed(),
        ephemeral=True
    )


# =========================================================
# /operation_logs
# 操作ログ確認
# =========================================================

@bot.tree.command(
    name="operation_logs",
    description="直近の操作ログを表示します"
)
@app_commands.check(admin_check)
async def operation_logs_command(
    interaction: discord.Interaction
):

    with connect() as con:

        rows = con.execute("""
            SELECT *
            FROM operation_logs
            ORDER BY id DESC
            LIMIT 15
        """).fetchall()

    if not rows:

        return await safe_ephemeral(
            interaction,
            "操作ログはありません。"
        )

    lines = []

    for row in rows:

        keys = row.keys()

        created_at = (
            row["created_at"]
            if "created_at" in keys
            else "日時不明"
        )

        action = (
            row["action"]
            if "action" in keys
            else "操作"
        )

        user_id = (
            row["user_id"]
            if "user_id" in keys
            else "不明"
        )

        details = (
            row["details"]
            if "details" in keys
            else ""
        )

        lines.append(
            f"`{created_at}` <@{user_id}> "
            f"**{action}**\n{str(details)[:150]}"
        )

    embed = discord.Embed(
        title="直近の操作ログ",
        description="\n\n".join(lines)[:4000],
        color=discord.Color.dark_grey()
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# スラッシュコマンドエラー処理
# =========================================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):

    if isinstance(
        error,
        app_commands.CheckFailure
    ):

        message = (
            "この操作は管理者のみ実行できます。"
        )

    else:

        LOG.exception(
            "Application command error",
            exc_info=error
        )

        message = (
            "コマンド実行中にエラーが発生しました。"
            "管理者に連絡してください。"
        )

    try:

        await safe_ephemeral(
            interaction,
            message
        )

    except Exception:

        LOG.exception(
            "Error response failed"
        )


# =========================================================
# Bot起動
# =========================================================

def main():

    if not TOKEN:

        raise RuntimeError(
            "DISCORD_TOKEN が設定されていません。"
        )

    bot.run(
        TOKEN
    )


if __name__ == "__main__":

    main()
