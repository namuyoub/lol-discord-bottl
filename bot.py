
"""
Nexus League Bot v5.3
Python 3.10+
discord.py 2.x
Render対応

Bot独自のデータベース・ローカルファイルへのデータ保存は行いません。
情報の管理にはDiscord上の投稿・チャンネルを使用します。
"""

from __future__ import annotations

import os
import re
import logging
import asyncio
import unicodedata

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from aiohttp import web


# =========================================================
# 基本設定
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN", "")

GUILD_ID = int(
    os.getenv("GUILD_ID", "1566019287473193063")
)

PORT = int(os.getenv("PORT", "10000"))

JST = ZoneInfo("Asia/Tokyo")

LOG = logging.getLogger("nexus")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)


# =========================================================
# チャンネルID
# =========================================================

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

# 大会投稿先
TOURNAMENT_CHANNEL_ID = 1566061702716329994


# =========================================================
# サーバー・ロールID
# =========================================================

# サーバーID
TARGET_GUILD_ID = 1566019287473193063

# ロールパネル用ロール
ROLE_NORMAL_ID = 1569579116750049380
ROLE_RANK_ID = 1569578957236473876
ROLE_CUSTOM_ID = 1569578833953427507
ROLE_TOURNAMENT_ID = 1569578720216358923

# 運営ロール
OPERATIONS_ROLE_ID = 1566029417522794496

# チーム関連カテゴリ
# IDが未指定のため、Noneの場合はサーバー直下に作成
TEAM_CATEGORY_ID = None

# マッチング関連カテゴリ
# IDが未指定のため、Noneの場合はサーバー直下に作成
MATCHING_CATEGORY_ID = None

# 運営報告送信先ユーザー
REPORT_USER_ID = 1392895521433321502


# =========================================================
# ロール設定
# =========================================================

ROLE_PANEL_CONFIG = [
    {
        "name": "ノーマル",
        "role_id": ROLE_NORMAL_ID,
        "emoji": "🎮",
    },
    {
        "name": "ランク",
        "role_id": ROLE_RANK_ID,
        "emoji": "🏆",
    },
    {
        "name": "カスタム",
        "role_id": ROLE_CUSTOM_ID,
        "emoji": "⚔️",
    },
    {
        "name": "大会",
        "role_id": ROLE_TOURNAMENT_ID,
        "emoji": "🥇",
    },
]

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


# =========================================================
# ポジション設定
# =========================================================

LANES = (
    "TOP",
    "JGL",
    "MID",
    "ADC",
    "SUP",
)


# =========================================================
# 募集の表示名
# =========================================================

RECRUIT_KIND_LABELS = {
    "normal": "ノーマル・ARAM",
    "duo": "デュオランク",
    "flex": "フレックス",
    "custom": "カスタム",
}


# =========================================================
# 共通日時処理
# =========================================================

def now_jst() -> datetime:
    """現在の日本時間を返す"""
    return datetime.now(JST)


def format_jst(value: datetime) -> str:
    """日時を日本時間の表示に変換する"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=JST)
    else:
        value = value.astimezone(JST)

    return value.strftime("%Y年%m月%d日 %H:%M")


# =========================================================
# 入力文字の正規化
# =========================================================

def normalize_input(value: str) -> str:
    """
    全角・半角の違いを統一する。
    例：
    ２１：００ → 21:00
    １１月２２日 → 11月22日
    """
    return unicodedata.normalize("NFKC", value).strip()


# =========================================================
# Discord表示名取得
# =========================================================

def get_member_display_name(
    member: discord.Member | discord.User
) -> str:
    """Discord上の表示名を取得する"""
    return member.display_name


# =========================================================
# ランク表示名取得
# =========================================================

def get_rank_label(rank_key: str) -> str:
    for key, label in RANKS:
        if key == rank_key:
            return label

    return rank_key


def get_rank_points(rank_key: str) -> int:
    return RANK_POINTS.get(rank_key, 0)


# =========================================================
# プレイヤー用ニックネーム生成
# =========================================================

def make_player_nickname(
    game_name: str,
    positions: list[str],
    rank_key: str,
) -> str:

    # Riot IDの#以降は表示しない
    clean_name = game_name.split("#", 1)[0].strip()

    # 使用ポジション
    lane_text = "/".join(positions)

    # ランク略称
    rank_text = RANK_SHORT_NAMES.get(
        rank_key,
        rank_key
    )

    nickname = f"{clean_name} / {lane_text} / {rank_text}"

    # Discordのニックネーム上限に合わせる
    return nickname[:32]


# =========================================================
# テキストチャンネル取得
# =========================================================

async def get_text_channel(
    bot: commands.Bot,
    channel_id: int,
) -> Optional[discord.TextChannel]:

    channel = bot.get_channel(channel_id)

    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            LOG.exception(
                "チャンネル取得失敗: %s",
                channel_id
            )
            return None

    if isinstance(channel, discord.TextChannel):
        return channel

    return None


# =========================================================
# 一時メッセージ送信
# =========================================================

async def safe_ephemeral(
    interaction: discord.Interaction,
    content: Optional[str] = None,
    *,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None,
) -> None:

    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                content=content,
                embed=embed,
                view=view,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                content=content,
                embed=embed,
                view=view,
                ephemeral=True,
            )

    except discord.HTTPException:
        LOG.exception("一時メッセージ送信失敗")


# =========================================================
# 運営権限確認
# =========================================================

def is_operations_member(
    member: discord.Member,
) -> bool:

    if member.guild_permissions.administrator:
        return True

    return any(
        role.id == OPERATIONS_ROLE_ID
        for role in member.roles
    )


async def admin_check(
    interaction: discord.Interaction,
) -> bool:

    if not isinstance(interaction.user, discord.Member):
        return False

    if is_operations_member(interaction.user):
        return True

    await safe_ephemeral(
        interaction,
        "このコマンドは運営のみ使用できます。"
    )

    return False


# =========================================================
# 日付入力処理
# =========================================================

def parse_custom_date(
    date_text: str,
    time_text: str,
) -> Optional[datetime]:
    """
    年なしの日付入力を受け付ける。
    例：
    11月22日
    11/22
    １１月２２日

    時間：
    21:00
    ２１：００
    """

    date_text = normalize_input(date_text)
    time_text = normalize_input(time_text)

    date_match = re.fullmatch(
        r"(\d{1,2})\s*月\s*(\d{1,2})\s*日?",
        date_text
    )

    if not date_match:
        date_match = re.fullmatch(
            r"(\d{1,2})\s*/\s*(\d{1,2})",
            date_text
        )

    if not date_match:
        return None

    month = int(date_match.group(1))
    day = int(date_match.group(2))

    time_match = re.fullmatch(
        r"(\d{1,2})\s*:\s*(\d{2})",
        time_text
    )

    if not time_match:
        return None

    hour = int(time_match.group(1))
    minute = int(time_match.group(2))

    if not 1 <= month <= 12:
        return None

    if not 0 <= hour <= 23:
        return None

    if not 0 <= minute <= 59:
        return None

    current_year = now_jst().year

    try:
        result = datetime(
            current_year,
            month,
            day,
            hour,
            minute,
            tzinfo=JST,
        )
    except ValueError:
        return None

    # すでに過ぎた日付なら翌年として扱う
    if result < now_jst():
        try:
            result = result.replace(
                year=current_year + 1
            )
        except ValueError:
            return None

    return result


# =========================================================
# 表示用の日付・時間
# =========================================================

def format_month_day(value: datetime) -> str:
    return f"{value.month}月{value.day}日"


def format_hour_minute(value: datetime) -> str:
    return value.strftime("%H:%M")


# =========================================================
# Discord投稿の取得
# =========================================================

async def fetch_message_safely(
    channel: discord.TextChannel,
    message_id: int,
) -> Optional[discord.Message]:

    try:
        return await channel.fetch_message(message_id)

    except (
        discord.NotFound,
        discord.Forbidden,
        discord.HTTPException,
    ):
        LOG.exception(
            "Discord投稿取得失敗: channel=%s message=%s",
            channel.id,
            message_id,
        )
        return None


# =========================================================
# Bot起動時の共通チェック
# =========================================================

def validate_config() -> None:

    if not TOKEN:
        raise RuntimeError(
            "環境変数 DISCORD_TOKEN が設定されていません。"
        )

    if not TARGET_GUILD_ID:
        raise RuntimeError(
            "サーバーIDが設定されていません。"
        )

    required_channels = [
        REGISTRATION_CHANNEL_ID,
        CUSTOM_CHANNEL_ID,
        TOURNAMENT_CHANNEL_ID,
        *RECRUIT_CHANNELS.values(),
    ]

    if any(not channel_id for channel_id in required_channels):
        raise RuntimeError(
            "チャンネルIDの設定に不足があります。"
        )

    LOG.info("設定チェック完了")


# =========================================================
# Part 2 / 6
# 通常募集・ランク募集・カスタム募集
# =========================================================


# =========================================================
# 募集参加者の読み取り
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


# =========================================================
# 参加者表示用Embed作成
# =========================================================

def make_participant_embed(
    original: discord.Embed,
    regular_ids: list[int],
    late_ids: list[int],
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
        inline=True,
    )

    embed.add_field(
        name=f"途中参加する（{len(late_ids)}名）",
        value="\n".join(
            f"<@{user_id}>"
            for user_id in late_ids
        ) or "なし",
        inline=True,
    )

    return embed


# =========================================================
# 募集スレッド作成
# =========================================================

async def create_recruit_thread(
    message: discord.Message,
    kind: str,
) -> Optional[discord.Thread]:

    if not message.guild:
        return None

    label = RECRUIT_KIND_LABELS.get(
        kind,
        "募集",
    )

    thread_name = (
        f"{label}｜{message.author.display_name}"
    )[:100]

    try:

        thread = await message.create_thread(
            name=thread_name,
            auto_archive_duration=1440,
        )

        await thread.send(
            f"{message.author.mention} さんの募集スレッドです。\n"
            "募集に関する連絡はこちらで行ってください。",
            allowed_mentions=discord.AllowedMentions(
                users=True
            ),
        )

        return thread

    except discord.HTTPException:

        LOG.exception(
            "募集スレッド作成失敗"
        )

        return None


# =========================================================
# 募集参加ボタン
# =========================================================

class RecruitmentView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    async def _change(
        self,
        interaction: discord.Interaction,
        status: str,
    ):

        if not interaction.guild:
            return await safe_ephemeral(
                interaction,
                "サーバー内の募集投稿から操作してください。",
            )

        message = interaction.message

        if message is None or not message.embeds:
            return await safe_ephemeral(
                interaction,
                "募集情報を読み取れませんでした。",
            )

        original_embed = message.embeds[0]

        regular_ids, late_ids = (
            get_recruitment_participants(
                original_embed
            )
        )

        user_id = interaction.user.id

        # いったん両方から削除する
        # これにより通常参加・途中参加の重複を防ぐ
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

        # withdrawの場合は追加しない
        new_embed = make_participant_embed(
            original_embed,
            regular_ids,
            late_ids,
        )

        try:

            await message.edit(
                embed=new_embed,
                view=self,
            )

        except discord.HTTPException:

            LOG.exception(
                "募集参加状況の更新失敗"
            )

            return await safe_ephemeral(
                interaction,
                "参加状況の更新に失敗しました。",
            )

        # 募集投稿に紐づくスレッドを取得
        thread = message.thread

        # スレッドが取得できない場合は検索
        if thread is None:

            try:

                active_threads = (
                    await interaction.guild.active_threads()
                )

                thread = discord.utils.get(
                    active_threads,
                    id=message.id,
                )

            except discord.HTTPException:

                thread = None

        # スレッドへの参加・退出
        if thread is not None:

            try:

                if status == "withdraw":

                    try:
                        await thread.remove_user(
                            interaction.user
                        )
                    except discord.HTTPException:
                        pass

                    await thread.send(
                        f"🚪 {interaction.user.mention} さんが辞退しました。",
                        allowed_mentions=discord.AllowedMentions(
                            users=True
                        ),
                    )

                else:

                    try:
                        await thread.add_user(
                            interaction.user
                        )
                    except discord.HTTPException:
                        pass

                    if status == "late":
                        label = "途中参加"
                    else:
                        label = "通常参加"

                    await thread.send(
                        f"🙋 {interaction.user.mention} さんが{label}しました。",
                        allowed_mentions=discord.AllowedMentions(
                            users=True
                        ),
                    )

            except discord.HTTPException:

                LOG.exception(
                    "募集スレッドへの通知失敗"
                )

        # 結果を本人に通知
        if status == "withdraw":

            result = "辞退しました。再参加できます。"

        elif status == "late":

            result = "途中参加を受け付けました。"

        else:

            result = "参加を受け付けました。"

        await safe_ephemeral(
            interaction,
            result,
        )

    # -----------------------------------------------------
    # 参加する
    # -----------------------------------------------------

    @discord.ui.button(
        label="参加する",
        style=discord.ButtonStyle.success,
        emoji="🙋",
        custom_id="nexus:v53:recruit:join",
    )
    async def join(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self._change(
            interaction,
            "regular",
        )

    # -----------------------------------------------------
    # 途中参加する
    # -----------------------------------------------------

    @discord.ui.button(
        label="途中参加する",
        style=discord.ButtonStyle.primary,
        emoji="⏩",
        custom_id="nexus:v53:recruit:late",
    )
    async def late(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self._change(
            interaction,
            "late",
        )

    # -----------------------------------------------------
    # 辞退する
    # -----------------------------------------------------

    @discord.ui.button(
        label="辞退する",
        style=discord.ButtonStyle.danger,
        emoji="🚪",
        custom_id="nexus:v53:recruit:withdraw",
    )
    async def withdraw(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self._change(
            interaction,
            "withdraw",
        )


# =========================================================
# 通常・ランク募集の自動処理
# =========================================================

async def process_normal_recruitment(
    message: discord.Message,
    kind: str,
):

    if not message.guild:
        return

    # すでにスレッドが作成されている場合は処理しない
    if message.thread is not None:
        return

    # 空投稿は処理しない
    if not message.content.strip() and not message.attachments:
        return

    # 募集スレッドを作成
    thread = await create_recruit_thread(
        message,
        kind,
    )

    if thread is None:

        await message.reply(
            "募集スレッドの作成に失敗しました。運営にお問い合わせください。",
            mention_author=False,
        )

        return

    # ロールを取得
    role_id = None

    if kind == "normal":
        role_id = ROLE_NORMAL_ID

    elif kind in ("duo", "flex"):
        role_id = ROLE_RANK_ID

    role = message.guild.get_role(
        role_id
    ) if role_id else None

    # 募集内容
    description = message.content.strip()

    if not description:
        description = "募集内容はスレッドをご確認ください。"

    embed = discord.Embed(
        title=f"募集：{RECRUIT_KIND_LABELS[kind]}",
        description=description[:4000],
        color=discord.Color.green(),
    )

    embed.add_field(
        name="募集主",
        value=message.author.mention,
        inline=False,
    )

    embed.add_field(
        name="参加する（0名）",
        value="なし",
        inline=True,
    )

    embed.add_field(
        name="途中参加する（0名）",
        value="なし",
        inline=True,
    )

    # 募集投稿そのものをボタン付き投稿にする
    try:

        await message.edit(
            content=(
                f"{role.mention if role else ''}\n"
                f"募集スレッド：{thread.mention}"
            ),
            embed=embed,
            view=RecruitmentView(),
            allowed_mentions=discord.AllowedMentions(
                roles=[role] if role else [],
                users=False,
            ),
        )

    except discord.HTTPException:

        LOG.exception(
            "募集投稿の更新失敗"
        )

        return

    LOG.info(
        "募集投稿を作成: kind=%s message=%s",
        kind,
        message.id,
    )


# =========================================================
# 通常・ランク募集チャンネルの監視
#
# Part 6のon_messageから呼び出す関数
# =========================================================

async def handle_recruitment_message(
    message: discord.Message,
):

    if message.author.bot:
        return

    if not message.guild:
        return

    channel_kind = None

    for kind, channel_id in RECRUIT_CHANNELS.items():

        if message.channel.id == channel_id:
            channel_kind = kind
            break

    if channel_kind is None:
        return

    await process_normal_recruitment(
        message,
        channel_kind,
    )


# =========================================================
# カスタム募集の作成モーダル
# =========================================================

class CustomRecruitmentModal(
    discord.ui.Modal,
    title="カスタム募集を作成",
):

    date_input = discord.ui.TextInput(
        label="日程（月日）",
        placeholder="例：11月22日",
        max_length=20,
        required=True,
    )

    time_input = discord.ui.TextInput(
        label="時間",
        placeholder="例：21:00",
        max_length=10,
        required=True,
    )

    title_input = discord.ui.TextInput(
        label="募集タイトル",
        placeholder="例：フルパカスタム募集",
        max_length=100,
        required=True,
    )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):

        if not interaction.guild:
            return await safe_ephemeral(
                interaction,
                "サーバー内で操作してください。",
            )

        # 日付・時間の確認
        date_text = normalize_input(
            self.date_input.value
        )

        time_text = normalize_input(
            self.time_input.value
        )

        target = parse_custom_date(
            date_text,
            time_text,
        )

        if target is None:
            return await safe_ephemeral(
                interaction,
                "日付または時間の形式が正しくありません。\n"
                "日程：11月22日\n"
                "時間：21:00\n"
                "のように入力してください。",
            )

        date_display = format_month_day(
            target
        )

        time_display = format_hour_minute(
            target
        )

        recruitment_title = normalize_input(
            self.title_input.value
        )

        if not recruitment_title:
            return await safe_ephemeral(
                interaction,
                "募集タイトルを入力してください。",
            )

        channel = await get_text_channel(
            interaction.client,
            CUSTOM_CHANNEL_ID,
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):
            return await safe_ephemeral(
                interaction,
                "カスタム募集チャンネルが見つかりません。",
            )

        role = interaction.guild.get_role(
            ROLE_CUSTOM_ID
        )

        # 日付・時間を大きく表示
        content = (
            f"{role.mention if role else ''}\n"
            f"## {date_display}\n"
            f"## {time_display}"
        )

        embed = discord.Embed(
            title=recruitment_title,
            color=discord.Color.purple(),
        )

        embed.add_field(
            name="募集主",
            value=interaction.user.mention,
            inline=False,
        )

        embed.add_field(
            name="参加する（0名）",
            value="なし",
            inline=True,
        )

        embed.add_field(
            name="途中参加する（0名）",
            value="なし",
            inline=True,
        )

        # 投稿する
        try:

            post = await channel.send(
                content=content,
                embed=embed,
                view=RecruitmentView(),
                allowed_mentions=discord.AllowedMentions(
                    roles=[role] if role else [],
                    users=False,
                ),
            )

            # 募集投稿にスレッドを作成
            thread = await create_recruit_thread(
                post,
                "custom",
            )

            if thread is None:

                await post.delete()

                return await safe_ephemeral(
                    interaction,
                    "募集スレッドの作成に失敗したため、募集投稿を取り消しました。",
                )

            # スレッド案内を投稿に反映
            await post.edit(
                content=(
                    f"{content}\n"
                    f"募集スレッド：{thread.mention}"
                ),
                view=RecruitmentView(),
            )

        except discord.HTTPException:

            LOG.exception(
                "カスタム募集投稿失敗"
            )

            return await safe_ephemeral(
                interaction,
                "カスタム募集の投稿に失敗しました。Botの権限を確認してください。",
            )

        # 投稿後、3件ごとに新しい募集ボタンを設置
        await update_custom_recruitment_panel(
            channel
        )

        await safe_ephemeral(
            interaction,
            "カスタム募集を投稿しました。",
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
        custom_id="nexus:v53:custom:create",
    )
    async def create(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await interaction.response.send_modal(
            CustomRecruitmentModal()
        )


# =========================================================
# カスタム募集投稿数の確認
#
# Bot内には投稿数を保存しない。
# Discord上の投稿を確認して数える。
# =========================================================

async def count_custom_recruitment_posts(
    channel: discord.TextChannel,
) -> int:

    total = 0

    async for message in channel.history(
        limit=5000,
        oldest_first=False,
    ):

        if message.author.id != channel.guild.me.id:
            continue

        if not message.embeds:
            continue

        embed = message.embeds[0]

        if embed.footer and embed.footer.text == "NEXUS_CUSTOM_RECRUITMENT":
            total += 1

    return total


# =========================================================
# カスタム募集ボタンを設置
# =========================================================

async def install_custom_recruitment_panel(
    channel: discord.TextChannel,
):

    embed = discord.Embed(
        title="カスタム募集",
        description="下のボタンからカスタム募集を作成できます。",
        color=discord.Color.blurple(),
    )

    await channel.send(
        embed=embed,
        view=CustomRecruitmentPanelView(),
    )


# =========================================================
# カスタム募集3件ごとの新パネル設置
# =========================================================

async def update_custom_recruitment_panel(
    channel: discord.TextChannel,
):

    total = await count_custom_recruitment_posts(
        channel
    )

    if total > 0 and total % 3 == 0:

        await install_custom_recruitment_panel(
            channel
        )


# =========================================================
# カスタム募集投稿に識別用フッターを付けるための補助
# =========================================================

def mark_custom_recruitment_embed(
    embed: discord.Embed,
) -> discord.Embed:

    embed.set_footer(
        text="NEXUS_CUSTOM_RECRUITMENT"
    )

    return embed


# =========================================================
# Part 3 / 6
# プレイヤー登録・ランク選択・ポジション複数選択
# OP.GG送信・Discordニックネーム変更
# =========================================================


# =========================================================
# ランク選択画面
# =========================================================

class RankSelect(discord.ui.Select):

    def __init__(self):

        options = []

        for rank_key, rank_label in RANKS:

            points = RANK_POINTS[rank_key]

            options.append(
                discord.SelectOption(
                    label=rank_label,
                    value=rank_key,
                    description=f"{points}ポイント",
                )
            )

        super().__init__(
            placeholder="登録するランクを1つ選択してください",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="nexus:v53:registration:rank",
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):

        selected_rank = self.values[0]

        await interaction.response.edit_message(
            content=(
                f"ランク：**{get_rank_label(selected_rank)}**\n\n"
                "次に、使用するポジションを選択してください。\n"
                "複数選択できます。"
            ),
            view=PositionSelectView(
                selected_rank
            ),
        )


class RankSelectView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=180)

        self.add_item(
            RankSelect()
        )


# =========================================================
# ポジション複数選択
# =========================================================

class PositionSelect(discord.ui.Select):

    def __init__(
        self,
        rank_key: str,
    ):

        self.rank_key = rank_key

        options = [
            discord.SelectOption(
                label="TOP",
                value="TOP",
                emoji="⚔️",
            ),
            discord.SelectOption(
                label="JGL",
                value="JGL",
                emoji="🌲",
            ),
            discord.SelectOption(
                label="MID",
                value="MID",
                emoji="🔮",
            ),
            discord.SelectOption(
                label="ADC",
                value="ADC",
                emoji="🏹",
            ),
            discord.SelectOption(
                label="SUP",
                value="SUP",
                emoji="🛡️",
            ),
        ]

        super().__init__(
            placeholder="ポジションを選択してください（複数選択可）",
            min_values=1,
            max_values=5,
            options=options,
            custom_id="nexus:v53:registration:positions",
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):

        selected_positions = self.values

        await interaction.response.send_modal(
            RegistrationModal(
                rank_key=self.rank_key,
                positions=selected_positions,
            )
        )


class PositionSelectView(discord.ui.View):

    def __init__(
        self,
        rank_key: str,
    ):

        super().__init__(timeout=180)

        self.add_item(
            PositionSelect(rank_key)
        )


# =========================================================
# プレイヤー登録モーダル
# =========================================================

class RegistrationModal(
    discord.ui.Modal,
    title="プレイヤー情報登録",
):

    riot_id = discord.ui.TextInput(
        label="Riot ID",
        placeholder="例：Player#JP1",
        max_length=80,
        required=True,
    )

    introduction = discord.ui.TextInput(
        label="自己紹介",
        placeholder="自己紹介を入力してください。",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True,
    )

    opgg_url = discord.ui.TextInput(
        label="OP.GGアドレス",
        placeholder="https://www.op.gg/...",
        max_length=300,
        required=True,
    )

    def __init__(
        self,
        rank_key: str,
        positions: list[str],
    ):

        super().__init__()

        self.rank_key = rank_key
        self.positions = positions

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):

        if not interaction.guild:

            return await safe_ephemeral(
                interaction,
                "サーバー内で登録してください。",
            )

        # -------------------------------------------------
        # 入力値の整理
        # -------------------------------------------------

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
                "Riot IDは「名前#タグ」の形式で入力してください。",
            )

        game_name, tag_line = riot_id_value.split(
            "#",
            1,
        )

        if not game_name.strip() or not tag_line.strip():

            return await safe_ephemeral(
                interaction,
                "Riot IDの名前とタグを正しく入力してください。",
            )

        # ランク確認
        rank_label = dict(RANKS).get(
            self.rank_key
        )

        if not rank_label:

            return await safe_ephemeral(
                interaction,
                "ランク情報が正しくありません。最初からやり直してください。",
            )

        # ポジション確認
        valid_positions = [
            position
            for position in self.positions
            if position in LANES
        ]

        if not valid_positions:

            return await safe_ephemeral(
                interaction,
                "ポジションを1つ以上選択してください。",
            )

        # -------------------------------------------------
        # OP.GG URL確認
        # -------------------------------------------------

        if not re.match(
            r"^https?://",
            opgg_value,
            flags=re.IGNORECASE,
        ):

            return await safe_ephemeral(
                interaction,
                "OP.GGアドレスは https:// から入力してください。",
            )

        opgg_domain = re.sub(
            r"^https?://",
            "",
            opgg_value,
            flags=re.IGNORECASE,
        ).split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]

        if not (
            opgg_domain.lower() == "op.gg"
            or opgg_domain.lower().endswith(".op.gg")
        ):

            return await safe_ephemeral(
                interaction,
                "OP.GGのアドレスを入力してください。",
            )

        # -------------------------------------------------
        # ランクポイント
        # -------------------------------------------------

        points = get_rank_points(
            self.rank_key
        )

        # -------------------------------------------------
        # 登録先チャンネル
        # -------------------------------------------------

        channel = await get_text_channel(
            interaction.client,
            REGISTRATION_CHANNEL_ID,
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):

            return await safe_ephemeral(
                interaction,
                "プレイヤー登録チャンネルが見つかりません。",
            )

        # -------------------------------------------------
        # 登録Embed作成
        # -------------------------------------------------

        member = interaction.user

        embed = discord.Embed(
            title="プレイヤー登録",
            color=discord.Color.blue(),
            timestamp=now_jst(),
        )

        embed.add_field(
            name="プレイヤー",
            value=member.mention,
            inline=False,
        )

        embed.add_field(
            name="Riot ID",
            value=discord.utils.escape_markdown(
                riot_id_value
            ),
            inline=True,
        )

        embed.add_field(
            name="ランク",
            value=rank_label,
            inline=True,
        )

        embed.add_field(
            name="ランクポイント",
            value=f"**{points} pt**",
            inline=True,
        )

        embed.add_field(
            name="ポジション",
            value=" / ".join(valid_positions),
            inline=False,
        )

        embed.add_field(
            name="自己紹介",
            value=introduction_value[:1024],
            inline=False,
        )

        embed.add_field(
            name="OP.GG",
            value=f"[プロフィールを開く]({opgg_value})",
            inline=False,
        )

        embed.set_footer(
            text="Nexus League プレイヤー登録"
        )

        # -------------------------------------------------
        # Discordチャンネルへ投稿
        # 投稿成功前に登録成功とは表示しない
        # -------------------------------------------------

        try:

            await channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    users=False,
                    roles=False,
                    everyone=False,
                ),
            )

        except discord.Forbidden:

            LOG.exception(
                "登録投稿の権限がありません"
            )

            return await safe_ephemeral(
                interaction,
                "登録情報を投稿できませんでした。Botにチャンネルへの投稿権限があるか確認してください。",
            )

        except discord.HTTPException:

            LOG.exception(
                "登録投稿に失敗しました"
            )

            return await safe_ephemeral(
                interaction,
                "登録情報の投稿に失敗しました。時間をおいて再度お試しください。",
            )

        # -------------------------------------------------
        # 投稿成功後にニックネームを変更
        # -------------------------------------------------

        nickname = make_player_nickname(
            game_name,
            valid_positions,
            self.rank_key,
        )

        nickname_changed = False

        if isinstance(
            interaction.user,
            discord.Member,
        ):

            try:

                await interaction.user.edit(
                    nick=nickname,
                    reason="Nexus League プレイヤー登録",
                )

                nickname_changed = True

            except discord.Forbidden:

                LOG.warning(
                    "ニックネーム変更権限がありません: %s",
                    interaction.user.id,
                )

            except discord.HTTPException:

                LOG.exception(
                    "ニックネーム変更失敗"
                )

        # -------------------------------------------------
        # 完了通知
        # -------------------------------------------------

        if nickname_changed:

            result = (
                "プレイヤー登録が完了しました。\n"
                "登録情報をチャンネルに投稿し、ニックネームも変更しました。"
            )

        else:

            result = (
                "プレイヤー登録情報の投稿が完了しました。\n"
                "ただし、ニックネームを変更できませんでした。"
                "Botのロール位置と権限を確認してください。"
            )

        await safe_ephemeral(
            interaction,
            result,
        )

        LOG.info(
            "プレイヤー登録投稿完了: user_id=%s",
            interaction.user.id,
        )


# =========================================================
# 登録開始コマンド
# =========================================================

@app_commands.command(
    name="register",
    description="Nexus Leagueのプレイヤー登録を開始します。",
)
async def register_command(
    interaction: discord.Interaction,
):

    if not interaction.guild:

        return await safe_ephemeral(
            interaction,
            "サーバー内で実行してください。",
        )

    await interaction.response.send_message(
        "## プレイヤー登録\n"
        "最初に現在のランクを1つ選択してください。",
        view=RankSelectView(),
        ephemeral=True,
    )


# =========================================================
# Part 4 / 6
# FAカード・ロールパネル・チーム受付
# =========================================================


# =========================================================
# ロールID
# =========================================================

ROLE_PANEL_ROLES = {
    "normal": {
        "name": "ノーマル",
        "id": 1569579116750049380,
        "emoji": "🎮",
    },
    "rank": {
        "name": "ランク",
        "id": 1569578957236473876,
        "emoji": "🏆",
    },
    "custom": {
        "name": "カスタム",
        "id": 1569578833953427507,
        "emoji": "👥",
    },
    "tournament": {
        "name": "大会",
        "id": 1569578720216358923,
        "emoji": "🥇",
    },
}

TEAM_OPERATIONS_ROLE_ID = 1566029417522794496

# カテゴリIDは未指定のため None
TEAM_REQUEST_CATEGORY_ID = None
MATCHING_REQUEST_CATEGORY_ID = None


# =========================================================
# チャンネル取得
# =========================================================

async def get_guild_text_channel(
    guild: discord.Guild,
    channel_id: int,
):
    channel = guild.get_channel(channel_id)

    if channel is None:
        try:
            channel = await guild.fetch_channel(channel_id)
        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
        ):
            return None

    if isinstance(channel, discord.TextChannel):
        return channel

    return None


# =========================================================
# FAカード入力モーダル
# =========================================================

class FaModal(
    discord.ui.Modal,
    title="FAカード登録",
):

    rank = discord.ui.TextInput(
        label="ランク",
        placeholder="例：Diamond I",
        max_length=50,
        required=True,
    )

    position = discord.ui.TextInput(
        label="希望ポジション",
        placeholder="例：MID / ADC",
        max_length=100,
        required=True,
    )

    introduction = discord.ui.TextInput(
        label="自己紹介・希望条件",
        placeholder="活動時間や希望条件など",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True,
    )

    opgg = discord.ui.TextInput(
        label="OP.GGアドレス",
        placeholder="https://www.op.gg/...",
        max_length=300,
        required=False,
    )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):

        if not interaction.guild:
            return await safe_ephemeral(
                interaction,
                "サーバー内で操作してください。",
            )

        # FAカードは運営メンバー限定
        if not is_operations_member(interaction.user):
            return await safe_ephemeral(
                interaction,
                "FAカードの登録は運営メンバーのみ利用できます。",
            )

        channel = await get_guild_text_channel(
            interaction.guild,
            REGISTRATION_CHANNEL_ID,
        )

        if channel is None:
            return await safe_ephemeral(
                interaction,
                "登録チャンネルが見つかりません。",
            )

        rank_text = normalize_input(self.rank.value)
        position_text = normalize_input(self.position.value)
        introduction_text = normalize_input(
            self.introduction.value
        )
        opgg_text = normalize_input(self.opgg.value)

        if not rank_text or not position_text:
            return await safe_ephemeral(
                interaction,
                "ランクと希望ポジションを入力してください。",
            )

        # OP.GGのURL確認
        if opgg_text:
            if not re.match(
                r"^https?://",
                opgg_text,
                flags=re.IGNORECASE,
            ):
                return await safe_ephemeral(
                    interaction,
                    "OP.GGアドレスは https:// から入力してください。",
                )

            domain = re.sub(
                r"^https?://",
                "",
                opgg_text,
                flags=re.IGNORECASE,
            ).split("/", 1)[0].split("?", 1)[0]

            if not (
                domain.lower() == "op.gg"
                or domain.lower().endswith(".op.gg")
            ):
                return await safe_ephemeral(
                    interaction,
                    "OP.GGのアドレスを入力してください。",
                )

        embed = discord.Embed(
            title="FAカード",
            description=(
                f"{interaction.user.mention} さんが"
                "FA情報を登録しました。"
            ),
            color=discord.Color.orange(),
            timestamp=now_jst(),
        )

        embed.add_field(
            name="ランク",
            value=rank_text[:1024],
            inline=True,
        )

        embed.add_field(
            name="希望ポジション",
            value=position_text[:1024],
            inline=True,
        )

        embed.add_field(
            name="自己紹介・希望条件",
            value=introduction_text[:1024],
            inline=False,
        )

        if opgg_text:
            embed.add_field(
                name="OP.GG",
                value=f"[OP.GGを開く]({opgg_text})",
                inline=False,
            )

        embed.set_footer(
            text=f"登録者ID：{interaction.user.id}"
        )

        try:
            await channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )

        except discord.Forbidden:
            LOG.exception("FAカード投稿の権限がありません")
            return await safe_ephemeral(
                interaction,
                "FAカードを投稿できません。Botのチャンネル権限を確認してください。",
            )

        except discord.HTTPException:
            LOG.exception("FAカード投稿に失敗しました")
            return await safe_ephemeral(
                interaction,
                "FAカードの投稿に失敗しました。",
            )

        await safe_ephemeral(
            interaction,
            "FAカードを登録しました。",
        )


# =========================================================
# FAカードパネル
# =========================================================

class FaPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="FAカードを登録する",
        style=discord.ButtonStyle.primary,
        emoji="📝",
        custom_id="nexus:v53:fa:register",
    )
    async def register(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not is_operations_member(interaction.user):
            return await safe_ephemeral(
                interaction,
                "FAカードの登録は運営メンバーのみ利用できます。",
            )

        await interaction.response.send_modal(
            FaModal()
        )


def build_fa_panel_embed() -> discord.Embed:

    return discord.Embed(
        title="FAカード登録",
        description=(
            "チームを探している方のFA情報を登録します。\n\n"
            "ランク・希望ポジション・自己紹介・OP.GGを入力して"
            "登録チャンネルに投稿します。"
        ),
        color=discord.Color.orange(),
    )


# =========================================================
# ロール付与・解除
# =========================================================

async def toggle_role(
    interaction: discord.Interaction,
    role_key: str,
):

    if not interaction.guild:
        return await safe_ephemeral(
            interaction,
            "サーバー内で操作してください。",
        )

    config = ROLE_PANEL_ROLES.get(role_key)

    if config is None:
        return await safe_ephemeral(
            interaction,
            "ロール情報が見つかりません。",
        )

    role = interaction.guild.get_role(
        config["id"]
    )

    if role is None:
        return await safe_ephemeral(
            interaction,
            f"「{config['name']}」ロールが見つかりません。",
        )

    if not isinstance(interaction.user, discord.Member):
        return await safe_ephemeral(
            interaction,
            "メンバー情報を取得できませんでした。",
        )

    member = interaction.user

    try:
        if role in member.roles:
            await member.remove_roles(
                role,
                reason="Nexus League ロールパネル",
            )

            return await safe_ephemeral(
                interaction,
                f"「{config['name']}」ロールを解除しました。",
            )

        await member.add_roles(
            role,
            reason="Nexus League ロールパネル",
        )

        return await safe_ephemeral(
            interaction,
            f"「{config['name']}」ロールを付与しました。",
        )

    except discord.Forbidden:
        return await safe_ephemeral(
            interaction,
            "ロールを変更できません。Botの権限とロールの位置を確認してください。",
        )

    except discord.HTTPException:
        LOG.exception("ロール変更に失敗しました")
        return await safe_ephemeral(
            interaction,
            "ロールの変更に失敗しました。",
        )


# =========================================================
# ロールパネルボタン
# =========================================================

class RoleToggleButton(discord.ui.Button):

    def __init__(
        self,
        role_key: str,
        config: dict,
    ):

        self.role_key = role_key

        super().__init__(
            label=config["name"],
            emoji=config["emoji"],
            style=discord.ButtonStyle.primary,
            custom_id=f"nexus:v53:role:{role_key}",
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):

        await toggle_role(
            interaction,
            self.role_key,
        )


class RolePanelView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

        for role_key, config in ROLE_PANEL_ROLES.items():
            self.add_item(
                RoleToggleButton(
                    role_key,
                    config,
                )
            )


def build_role_panel_embed() -> discord.Embed:

    embed = discord.Embed(
        title="ロール選択",
        description=(
            "希望するロールのボタンを押してください。\n\n"
            "すでに所持しているロールを押すと解除されます。"
        ),
        color=discord.Color.blurple(),
    )

    for config in ROLE_PANEL_ROLES.values():
        embed.add_field(
            name=f"{config['emoji']} {config['name']}",
            value="ボタンで付与・解除できます。",
            inline=True,
        )

    return embed


# =========================================================
# チーム関連チャンネルの権限設定
# =========================================================

def make_private_channel_overwrites(
    guild: discord.Guild,
    member: discord.Member,
):

    bot_member = guild.me

    if bot_member is None:
        raise RuntimeError("Botのメンバー情報を取得できません。")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False,
        ),
        member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
        ),
        bot_member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True,
        ),
    }

    operations_role = guild.get_role(
        TEAM_OPERATIONS_ROLE_ID
    )

    if operations_role:
        overwrites[operations_role] = (
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )
        )

    return overwrites


# =========================================================
# チーム結成モーダル
# =========================================================

class TeamCreateModal(
    discord.ui.Modal,
    title="チーム結成",
):

    team_name = discord.ui.TextInput(
        label="チーム名",
        placeholder="チーム名を入力してください",
        max_length=80,
        required=True,
    )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):

        if not interaction.guild:
            return await safe_ephemeral(
                interaction,
                "サーバー内で操作してください。",
            )

        if not isinstance(interaction.user, discord.Member):
            return await safe_ephemeral(
                interaction,
                "メンバー情報を取得できませんでした。",
            )

        team_name_value = normalize_input(
            self.team_name.value
        )

        if not team_name_value:
            return await safe_ephemeral(
                interaction,
                "チーム名を入力してください。",
            )

        category = None

        if TEAM_REQUEST_CATEGORY_ID:
            candidate = interaction.guild.get_channel(
                TEAM_REQUEST_CATEGORY_ID
            )

            if isinstance(candidate, discord.CategoryChannel):
                category = candidate

        try:
            channel = await interaction.guild.create_text_channel(
                name="チーム結成",
                category=category,
                overwrites=make_private_channel_overwrites(
                    interaction.guild,
                    interaction.user,
                ),
                topic=(
                    f"チーム名：{team_name_value} / "
                    f"申請者ID：{interaction.user.id}"
                ),
                reason="Nexus League チーム結成申請",
            )

            await channel.send(
                f"{interaction.user.mention} さんのチーム結成申請です。\n\n"
                f"**チーム名：{discord.utils.escape_markdown(team_name_value)}**\n\n"
                "メンバー構成・募集条件・活動時間などを"
                "このチャンネルで入力してください。",
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                ),
            )

        except discord.Forbidden:
            return await safe_ephemeral(
                interaction,
                "チャンネルを作成できません。Botにチャンネル管理権限があるか確認してください。",
            )

        except discord.HTTPException:
            LOG.exception("チーム結成チャンネル作成失敗")
            return await safe_ephemeral(
                interaction,
                "チーム結成チャンネルの作成に失敗しました。",
            )

        await safe_ephemeral(
            interaction,
            f"チーム結成チャンネルを作成しました：{channel.mention}",
        )


# =========================================================
# チーム解散モーダル
# =========================================================

class TeamDisbandModal(
    discord.ui.Modal,
    title="チーム解散申請",
):

    team_name = discord.ui.TextInput(
        label="チーム名",
        placeholder="解散するチーム名",
        max_length=80,
        required=True,
    )

    reason = discord.ui.TextInput(
        label="解散理由",
        placeholder="解散理由を入力してください",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):

        if not interaction.guild:
            return await safe_ephemeral(
                interaction,
                "サーバー内で操作してください。",
            )

        if not isinstance(interaction.user, discord.Member):
            return await safe_ephemeral(
                interaction,
                "メンバー情報を取得できませんでした。",
            )

        team_name_value = normalize_input(
            self.team_name.value
        )

        reason_value = (
            normalize_input(self.reason.value)
            or "未記入"
        )

        if not team_name_value:
            return await safe_ephemeral(
                interaction,
                "チーム名を入力してください。",
            )

        category = None

        if TEAM_REQUEST_CATEGORY_ID:
            candidate = interaction.guild.get_channel(
                TEAM_REQUEST_CATEGORY_ID
            )

            if isinstance(candidate, discord.CategoryChannel):
                category = candidate

        try:
            channel = await interaction.guild.create_text_channel(
                name="チーム解散",
                category=category,
                overwrites=make_private_channel_overwrites(
                    interaction.guild,
                    interaction.user,
                ),
                topic=(
                    f"解散申請：{team_name_value} / "
                    f"申請者ID：{interaction.user.id}"
                ),
                reason="Nexus League チーム解散申請",
            )

            await channel.send(
                f"{interaction.user.mention} さんのチーム解散申請です。\n\n"
                f"**チーム名：{discord.utils.escape_markdown(team_name_value)}**\n"
                f"**解散理由：**\n{reason_value}\n\n"
                "運営と確認を進めてください。",
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                ),
            )

        except discord.Forbidden:
            return await safe_ephemeral(
                interaction,
                "チーム解散チャンネルを作成できません。Botの権限を確認してください。",
            )

        except discord.HTTPException:
            LOG.exception("チーム解散チャンネル作成失敗")
            return await safe_ephemeral(
                interaction,
                "チーム解散チャンネルの作成に失敗しました。",
            )

        await safe_ephemeral(
            interaction,
            f"チーム解散申請チャンネルを作成しました：{channel.mention}",
        )


# =========================================================
# マッチング希望チャンネル作成
# =========================================================

async def create_matching_channel(
    interaction: discord.Interaction,
):

    if not interaction.guild:
        return await safe_ephemeral(
            interaction,
            "サーバー内で操作してください。",
        )

    if not isinstance(interaction.user, discord.Member):
        return await safe_ephemeral(
            interaction,
            "メンバー情報を取得できませんでした。",
        )

    category = None

    if MATCHING_REQUEST_CATEGORY_ID:
        candidate = interaction.guild.get_channel(
            MATCHING_REQUEST_CATEGORY_ID
        )

        if isinstance(candidate, discord.CategoryChannel):
            category = candidate

    try:
        channel = await interaction.guild.create_text_channel(
            name="マッチング希望",
            category=category,
            overwrites=make_private_channel_overwrites(
                interaction.guild,
                interaction.user,
            ),
            topic=f"申請者ID：{interaction.user.id}",
            reason="Nexus League マッチング希望受付",
        )

        await channel.send(
            f"{interaction.user.mention} さんのマッチング希望チャンネルです。\n\n"
            "希望するゲームモード・ランク・ポジション・"
            "活動時間などを、このチャンネルで入力してください。",
            allowed_mentions=discord.AllowedMentions(
                users=True,
            ),
        )

    except discord.Forbidden:
        return await safe_ephemeral(
            interaction,
            "マッチング希望チャンネルを作成できません。Botの権限を確認してください。",
        )

    except discord.HTTPException:
        LOG.exception("マッチング希望チャンネル作成失敗")
        return await safe_ephemeral(
            interaction,
            "マッチング希望チャンネルの作成に失敗しました。",
        )

    await safe_ephemeral(
        interaction,
        f"マッチング希望チャンネルを作成しました：{channel.mention}",
    )


# =========================================================
# チーム・マッチング受付パネル
# =========================================================

class RequestPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="チーム結成",
        style=discord.ButtonStyle.success,
        emoji="🛡️",
        custom_id="nexus:v53:request:team_create",
    )
    async def team_create(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.send_modal(
            TeamCreateModal()
        )

    @discord.ui.button(
        label="チーム解散",
        style=discord.ButtonStyle.danger,
        emoji="🗑️",
        custom_id="nexus:v53:request:team_disband",
    )
    async def team_disband(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.send_modal(
            TeamDisbandModal()
        )

    @discord.ui.button(
        label="マッチング希望",
        style=discord.ButtonStyle.primary,
        emoji="🔎",
        custom_id="nexus:v53:request:matching",
    )
    async def matching(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await create_matching_channel(
            interaction
        )


def build_request_panel_embed() -> discord.Embed:

    return discord.Embed(
        title="チーム・マッチング受付",
        description=(
            "希望する項目のボタンを押してください。\n\n"
            "🛡️ **チーム結成**\n"
            "チーム名を入力して専用チャンネルを作成します。\n\n"
            "🗑️ **チーム解散**\n"
            "チーム名と解散理由を入力して申請します。\n\n"
            "🔎 **マッチング希望**\n"
            "ボタンを押すと専用チャンネルを作成します。"
        ),
        color=discord.Color.blurple(),
    )


# =========================================================
# Part 5 / 6
# 大会作成・大会参加・参加辞退
# Discord投稿を大会情報の保存場所として使用
# =========================================================


# =========================================================
# 大会日時の入力解析
# 入力例：11月22日 21:00
# 全角・半角どちらも受け付ける
# =========================================================

def parse_tournament_datetime(value: str):

    value = normalize_input(value)

    match = re.match(
        r"^(.+?)\s+([0-9]{1,2}:[0-9]{2})$",
        value,
    )

    if not match:
        return None

    date_text = match.group(1).strip()
    time_text = match.group(2).strip()

    return parse_custom_date(
        date_text,
        time_text,
    )


# =========================================================
# 大会Embedの参加チーム取得
# =========================================================

def get_tournament_participant_lines(
    embed: discord.Embed,
):

    for field in embed.fields:

        if field.name.startswith("参加チーム"):

            if field.value == "まだ参加チームはありません。":
                return []

            return [
                line
                for line in field.value.splitlines()
                if line.strip()
            ]

    return []


# =========================================================
# 大会Embedの参加チーム欄更新
# =========================================================

def update_tournament_participants(
    embed: discord.Embed,
    participant_lines: list[str],
):

    for index, field in enumerate(embed.fields):

        if field.name.startswith("参加チーム"):

            embed.remove_field(index)
            break

    if participant_lines:

        participant_text = "\n".join(
            participant_lines
        )

    else:

        participant_text = "まだ参加チームはありません。"

    embed.add_field(
        name=f"参加チーム（{len(participant_lines)}チーム）",
        value=participant_text[:1024],
        inline=False,
    )


# =========================================================
# 大会投稿の締切情報取得
# =========================================================

def get_tournament_deadline(
    embed: discord.Embed,
):

    footer_text = (
        embed.footer.text
        if embed.footer
        else ""
    )

    match = re.search(
        r"NEXUS_TOURNAMENT\|(.+)$",
        footer_text,
    )

    if not match:
        return None

    try:

        deadline = datetime.fromisoformat(
            match.group(1)
        )

        if deadline.tzinfo is None:
            deadline = deadline.replace(
                tzinfo=JST
            )

        return deadline.astimezone(JST)

    except ValueError:

        return None


# =========================================================
# 大会投稿の確認
# =========================================================

def is_tournament_message(
    message: discord.Message,
):

    if not message.embeds:
        return False

    embed = message.embeds[0]

    if not embed.footer:
        return False

    return embed.footer.text.startswith(
        "NEXUS_TOURNAMENT|"
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
        required=True,
    )

    def __init__(
        self,
        message_id: int,
        channel_id: int,
        action: str,
    ):

        self.message_id = message_id
        self.channel_id = channel_id
        self.action = action

        if action == "join":

            title = "大会に参加する"

        else:

            title = "大会を辞退する"

        super().__init__(
            title=title,
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):

        if not interaction.guild:

            return await safe_ephemeral(
                interaction,
                "サーバー内で操作してください。",
            )

        team_name_value = normalize_input(
            self.team_name.value
        )

        if not team_name_value:

            return await safe_ephemeral(
                interaction,
                "チーム名を入力してください。",
            )

        channel = await get_text_channel(
            interaction.client,
            self.channel_id,
        )

        if not isinstance(
            channel,
            discord.TextChannel,
        ):

            return await safe_ephemeral(
                interaction,
                "大会チャンネルが見つかりません。",
            )

        try:

            message = await channel.fetch_message(
                self.message_id
            )

        except discord.NotFound:

            return await safe_ephemeral(
                interaction,
                "大会投稿が見つかりません。",
            )

        except discord.HTTPException:

            LOG.exception(
                "大会投稿の取得に失敗しました"
            )

            return await safe_ephemeral(
                interaction,
                "大会投稿を取得できませんでした。",
            )

        if not is_tournament_message(message):

            return await safe_ephemeral(
                interaction,
                "この投稿は大会受付の投稿ではありません。",
            )

        embed = message.embeds[0].copy()

        # -------------------------------------------------
        # 参加締切確認
        # -------------------------------------------------

        deadline = get_tournament_deadline(
            embed
        )

        if deadline is None:

            return await safe_ephemeral(
                interaction,
                "大会の参加締切を読み取れません。",
            )

        if now_jst() > deadline:

            return await safe_ephemeral(
                interaction,
                "参加締切を過ぎています。",
            )

        # -------------------------------------------------
        # 現在の参加チーム一覧
        # -------------------------------------------------

        participant_lines = get_tournament_participant_lines(
            embed
        )

        user_marker = f"<@{interaction.user.id}>"

        existing_line = next(
            (
                line
                for line in participant_lines
                if user_marker in line
            ),
            None,
        )

        # -------------------------------------------------
        # 参加処理
        # -------------------------------------------------

        if self.action == "join":

            if existing_line:

                return await safe_ephemeral(
                    interaction,
                    "すでにこの大会へ参加登録されています。",
                )

            safe_team_name = discord.utils.escape_markdown(
                team_name_value
            )

            participant_lines.append(
                f"**{safe_team_name}** — {user_marker}"
            )

            update_tournament_participants(
                embed,
                participant_lines,
            )

            try:

                await message.edit(
                    embed=embed,
                    view=TournamentPanelView(),
                )

            except discord.HTTPException:

                LOG.exception(
                    "大会参加一覧の更新に失敗しました"
                )

                return await safe_ephemeral(
                    interaction,
                    "参加登録の更新に失敗しました。",
                )

            return await safe_ephemeral(
                interaction,
                f"「{team_name_value}」で大会参加登録しました。",
            )

        # -------------------------------------------------
        # 辞退処理
        # -------------------------------------------------

        if existing_line is None:

            return await safe_ephemeral(
                interaction,
                "この大会への参加登録が見つかりません。",
            )

        # 登録時のチーム名と入力内容を照合
        registered_team_name = existing_line.split(
            " — ",
            1,
        )[0]

        registered_team_name = (
            registered_team_name
            .replace("**", "")
        )

        if registered_team_name != discord.utils.escape_markdown(
            team_name_value
        ):

            return await safe_ephemeral(
                interaction,
                "入力されたチーム名が参加登録時の名前と一致しません。\n"
                "登録したチーム名をそのまま入力してください。",
            )

        participant_lines.remove(
            existing_line
        )

        update_tournament_participants(
            embed,
            participant_lines,
        )

        try:

            await message.edit(
                embed=embed,
                view=TournamentPanelView(),
            )

        except discord.HTTPException:

            LOG.exception(
                "大会辞退一覧の更新に失敗しました"
            )

            return await safe_ephemeral(
                interaction,
                "辞退処理の更新に失敗しました。",
            )

        await safe_ephemeral(
            interaction,
            f"「{team_name_value}」の大会参加を辞退しました。",
        )


# =========================================================
# 大会参加パネル
# =========================================================

class TournamentPanelView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="大会に参加する",
        style=discord.ButtonStyle.success,
        emoji="🏆",
        custom_id="nexus:v53:tournament:join",
    )
    async def join(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        if not interaction.message:

            return await safe_ephemeral(
                interaction,
                "大会投稿を取得できませんでした。",
            )

        await interaction.response.send_modal(
            TournamentEntryModal(
                message_id=interaction.message.id,
                channel_id=interaction.channel_id,
                action="join",
            )
        )

    @discord.ui.button(
        label="参加を辞退する",
        style=discord.ButtonStyle.danger,
        emoji="🚪",
        custom_id="nexus:v53:tournament:withdraw",
    )
    async def withdraw(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        if not interaction.message:

            return await safe_ephemeral(
                interaction,
                "大会投稿を取得できませんでした。",
            )

        await interaction.response.send_modal(
            TournamentEntryModal(
                message_id=interaction.message.id,
                channel_id=interaction.channel_id,
                action="withdraw",
            )
        )


# =========================================================
# 大会作成モーダル
# =========================================================

class TournamentCreateModal(
    discord.ui.Modal,
    title="大会を作成",
):

    name = discord.ui.TextInput(
        label="大会名",
        placeholder="大会名を入力してください",
        max_length=100,
        required=True,
    )

    starts_at_input = discord.ui.TextInput(
        label="開催日時",
        placeholder="例：11月22日 21:00",
        max_length=40,
        required=True,
    )

    deadline_input = discord.ui.TextInput(
        label="参加締切日時",
        placeholder="例：11月20日 23:00",
        max_length=40,
        required=True,
    )

    rules = discord.ui.TextInput(
        label="大会ルール・備考",
        placeholder="参加条件やルールを入力してください",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):

        if not interaction.guild:

            return await safe_ephemeral(
                interaction,
                "サーバー内で操作してください。",
            )

        # 運営ロールまたは管理者のみ作成可能
        if not is_operations_member(interaction.user):

            return await safe_ephemeral(
                interaction,
                "大会作成は運営メンバーのみ実行できます。",
            )

        tournament_name = normalize_input(
            self.name.value
        )

        starts_at = parse_tournament_datetime(
            self.starts_at_input.value
        )

        deadline_at = parse_tournament_datetime(
            self.deadline_input.value
        )

        if not tournament_name:

            return await safe_ephemeral(
                interaction,
                "大会名を入力してください。",
            )

        if starts_at is None:

            return await safe_ephemeral(
                interaction,
                "開催日時の形式が正しくありません。\n"
                "例：11月22日 21:00",
            )

        if deadline_at is None:

            return await safe_ephemeral(
                interaction,
                "参加締切日時の形式が正しくありません。\n"
                "例：11月20日 23:00",
            )

        if deadline_at >= starts_at:

            return await safe_ephemeral(
                interaction,
                "参加締切は大会開催日時より前に設定してください。",
            )

        if deadline_at <= now_jst():

            return await safe_ephemeral(
                interaction,
                "参加締切は現在より未来の日時にしてください。",
            )

        channel = await get_text_channel(
            interaction.client,
            TOURNAMENT_CHANNEL_ID,
        )

        if channel is None:

            return await safe_ephemeral(
                interaction,
                "大会投稿チャンネルが見つかりません。",
            )

        rules_text = (
            normalize_input(self.rules.value)
            or "詳細は運営から案内します。"
        )

        embed = discord.Embed(
            title=f"🏆 {discord.utils.escape_markdown(tournament_name)}",
            description=(
                f"## 開催日時\n"
                f"# {format_month_day(starts_at)} "
                f"{format_hour_minute(starts_at)}\n\n"
                f"## 参加締切\n"
                f"# {format_month_day(deadline_at)} "
                f"{format_hour_minute(deadline_at)}"
            ),
            color=discord.Color.gold(),
            timestamp=now_jst(),
        )

        embed.add_field(
            name="大会ルール・備考",
            value=rules_text[:1024],
            inline=False,
        )

        embed.add_field(
            name="参加チーム（0チーム）",
            value="まだ参加チームはありません。",
            inline=False,
        )

        # 締切日時はDiscord投稿のFooterに保持
        embed.set_footer(
            text=f"NEXUS_TOURNAMENT|{deadline_at.isoformat()}"
        )

        try:

            message = await channel.send(
                embed=embed,
                view=TournamentPanelView(),
                allowed_mentions=discord.AllowedMentions.none(),
            )

        except discord.Forbidden:

            LOG.exception(
                "大会投稿の権限がありません"
            )

            return await safe_ephemeral(
                interaction,
                "大会を投稿できません。Botの投稿権限を確認してください。",
            )

        except discord.HTTPException:

            LOG.exception(
                "大会投稿に失敗しました"
            )

            return await safe_ephemeral(
                interaction,
                "大会の投稿に失敗しました。",
            )

        await safe_ephemeral(
            interaction,
            f"大会を投稿しました。\n{message.jump_url}",
        )


# =========================================================
# 大会作成パネル
# =========================================================

class TournamentCreatePanelView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="大会を作成する",
        style=discord.ButtonStyle.primary,
        emoji="🏆",
        custom_id="nexus:v53:tournament:create",
    )
    async def create(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        if not is_operations_member(interaction.user):

            return await safe_ephemeral(
                interaction,
                "大会作成は運営メンバーのみ実行できます。",
            )

        await interaction.response.send_modal(
            TournamentCreateModal()
        )


def build_tournament_create_embed() -> discord.Embed:

    return discord.Embed(
        title="大会作成パネル",
        description=(
            "運営メンバーは下のボタンから大会を作成できます。\n\n"
            "大会名・開催日時・参加締切・ルールを入力してください。\n"
            "大会投稿には参加・辞退ボタンが表示されます。"
        ),
        color=discord.Color.gold(),
    )


# =========================================================
# Part 6 / 6
# Bot起動・イベント接続・パネル設置・Render対応
# =========================================================


# =========================================================
# Discord Bot設定
# =========================================================

intents = discord.Intents.default()

intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
)


# =========================================================
# Bot起動時の準備
# =========================================================

class NexusBot(commands.Bot):

    async def setup_hook(self):

        # -------------------------------------------------
        # 再起動後もボタンを動かすための永続View登録
        # -------------------------------------------------

        self.add_view(
            RecruitmentView()
        )

        self.add_view(
            CustomRecruitmentPanelView()
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
            TournamentPanelView()
        )

        self.add_view(
            TournamentCreatePanelView()
        )

        # -------------------------------------------------
        # スラッシュコマンド登録
        # -------------------------------------------------

        self.tree.add_command(
            register_command
        )

        self.tree.add_command(
            setup_role_panel_command
        )

        self.tree.add_command(
            setup_fa_panel_command
        )

        self.tree.add_command(
            setup_request_panel_command
        )

        self.tree.add_command(
            setup_tournament_panel_command
        )

        self.tree.add_command(
            setup_custom_recruitment_command
        )

        # -------------------------------------------------
        # 指定サーバーへコマンド同期
        # -------------------------------------------------

        guild = discord.Object(
            id=TARGET_GUILD_ID
        )

        try:

            synced = await self.tree.sync(
                guild=guild
            )

            LOG.info(
                "スラッシュコマンド同期完了: %s個",
                len(synced),
            )

        except discord.HTTPException:

            LOG.exception(
                "スラッシュコマンド同期失敗"
            )


# 上で作成したBotを使用
bot = NexusBot(
    command_prefix="!",
    intents=intents,
)


# =========================================================
# 運営権限確認
# =========================================================

def is_panel_manager(
    member: discord.Member,
) -> bool:

    if member.guild_permissions.administrator:
        return True

    return is_operations_member(
        member
    )


# =========================================================
# パネル設置権限確認
# =========================================================

async def check_panel_permission(
    interaction: discord.Interaction,
) -> bool:

    if not isinstance(
        interaction.user,
        discord.Member,
    ):

        await safe_ephemeral(
            interaction,
            "メンバー情報を取得できませんでした。",
        )

        return False

    if not is_panel_manager(
        interaction.user
    ):

        await safe_ephemeral(
            interaction,
            "この操作は運営メンバーのみ実行できます。",
        )

        return False

    return True


# =========================================================
# ロールパネル設置コマンド
# =========================================================

@app_commands.command(
    name="setup_role_panel",
    description="ロール選択パネルを設置します。",
)
async def setup_role_panel_command(
    interaction: discord.Interaction,
):

    if not await check_panel_permission(interaction):
        return

    if not isinstance(
        interaction.channel,
        discord.TextChannel,
    ):

        return await safe_ephemeral(
            interaction,
            "テキストチャンネルで実行してください。",
        )

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        message = await interaction.channel.send(
            embed=build_role_panel_embed(),
            view=RolePanelView(),
        )

    except discord.Forbidden:

        return await safe_ephemeral(
            interaction,
            "パネルを設置できません。Botの投稿権限を確認してください。",
        )

    except discord.HTTPException:

        LOG.exception(
            "ロールパネル設置失敗"
        )

        return await safe_ephemeral(
            interaction,
            "ロールパネルの設置に失敗しました。",
        )

    await safe_ephemeral(
        interaction,
        f"ロールパネルを設置しました。\n{message.jump_url}",
    )


# =========================================================
# FAカードパネル設置コマンド
# =========================================================

@app_commands.command(
    name="setup_fa_panel",
    description="FAカード登録パネルを設置します。",
)
async def setup_fa_panel_command(
    interaction: discord.Interaction,
):

    if not await check_panel_permission(interaction):
        return

    if not isinstance(
        interaction.channel,
        discord.TextChannel,
    ):

        return await safe_ephemeral(
            interaction,
            "テキストチャンネルで実行してください。",
        )

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        message = await interaction.channel.send(
            embed=build_fa_panel_embed(),
            view=FaPanelView(),
        )

    except discord.Forbidden:

        return await safe_ephemeral(
            interaction,
            "FAパネルを設置できません。Botの投稿権限を確認してください。",
        )

    except discord.HTTPException:

        LOG.exception(
            "FAパネル設置失敗"
        )

        return await safe_ephemeral(
            interaction,
            "FAパネルの設置に失敗しました。",
        )

    await safe_ephemeral(
        interaction,
        f"FAカードパネルを設置しました。\n{message.jump_url}",
    )


# =========================================================
# チーム・マッチング受付パネル設置コマンド
# =========================================================

@app_commands.command(
    name="setup_request_panel",
    description="チーム・マッチング受付パネルを設置します。",
)
async def setup_request_panel_command(
    interaction: discord.Interaction,
):

    if not await check_panel_permission(interaction):
        return

    if not isinstance(
        interaction.channel,
        discord.TextChannel,
    ):

        return await safe_ephemeral(
            interaction,
            "テキストチャンネルで実行してください。",
        )

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        message = await interaction.channel.send(
            embed=build_request_panel_embed(),
            view=RequestPanelView(),
        )

    except discord.Forbidden:

        return await safe_ephemeral(
            interaction,
            "受付パネルを設置できません。Botの投稿権限を確認してください。",
        )

    except discord.HTTPException:

        LOG.exception(
            "受付パネル設置失敗"
        )

        return await safe_ephemeral(
            interaction,
            "受付パネルの設置に失敗しました。",
        )

    await safe_ephemeral(
        interaction,
        f"受付パネルを設置しました。\n{message.jump_url}",
    )


# =========================================================
# 大会作成パネル設置コマンド
# =========================================================

@app_commands.command(
    name="setup_tournament_panel",
    description="大会作成パネルを設置します。",
)
async def setup_tournament_panel_command(
    interaction: discord.Interaction,
):

    if not await check_panel_permission(interaction):
        return

    if not isinstance(
        interaction.channel,
        discord.TextChannel,
    ):

        return await safe_ephemeral(
            interaction,
            "テキストチャンネルで実行してください。",
        )

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        message = await interaction.channel.send(
            embed=build_tournament_create_embed(),
            view=TournamentCreatePanelView(),
        )

    except discord.Forbidden:

        return await safe_ephemeral(
            interaction,
            "大会作成パネルを設置できません。Botの投稿権限を確認してください。",
        )

    except discord.HTTPException:

        LOG.exception(
            "大会作成パネル設置失敗"
        )

        return await safe_ephemeral(
            interaction,
            "大会作成パネルの設置に失敗しました。",
        )

    await safe_ephemeral(
        interaction,
        f"大会作成パネルを設置しました。\n{message.jump_url}",
    )


# =========================================================
# カスタム募集パネル設置コマンド
# =========================================================

@app_commands.command(
    name="setup_custom_recruitment",
    description="カスタム募集パネルを設置・更新します。",
)
async def setup_custom_recruitment_command(
    interaction: discord.Interaction,
):

    if not await check_panel_permission(interaction):
        return

    await interaction.response.defer(
        ephemeral=True
    )

    try:

        await install_custom_recruitment_panel()

    except Exception:

        LOG.exception(
            "カスタム募集パネル設置失敗"
        )

        return await safe_ephemeral(
            interaction,
            "カスタム募集パネルの設置に失敗しました。チャンネルIDとBotの権限を確認してください。",
        )

    await safe_ephemeral(
        interaction,
        "カスタム募集パネルの設置処理が完了しました。",
    )


# =========================================================
# メッセージ投稿イベント
# =========================================================

@bot.event
async def on_message(
    message: discord.Message,
):

    # Bot自身・他Botの投稿は無視
    if message.author.bot:
        return

    # サーバー外のメッセージは無視
    if message.guild is None:
        return

    try:

        await handle_recruitment_message(
            message
        )

    except Exception:

        LOG.exception(
            "募集メッセージ処理中にエラーが発生しました"
        )

    # command_prefixを使用する場合に必要
    await bot.process_commands(
        message
    )


# =========================================================
# Bot起動イベント
# =========================================================

@bot.event
async def on_ready():

    LOG.info(
        "===================================="
    )

    LOG.info(
        "Nexus League Bot 起動完了"
    )

    LOG.info(
        "Bot名：%s",
        bot.user,
    )

    LOG.info(
        "Bot ID：%s",
        bot.user.id if bot.user else "不明",
    )

    LOG.info(
        "接続サーバー数：%s",
        len(bot.guilds),
    )

    LOG.info(
        "===================================="


    )


# =========================================================
# Render稼働確認用Webサーバー
# =========================================================

async def health_check(
    request: web.Request,
):

    return web.Response(
        text="Nexus League Bot is running.",
        status=200,
    )


async def start_web_server():

    app = web.Application()

    app.router.add_get(
        "/",
        health_check,
    )

    app.router.add_get(
        "/health",
        health_check,
    )

    runner = web.AppRunner(
        app
    )

    await runner.setup()

    port = int(
        os.getenv(
            "PORT",
            "10000",
        )
    )

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port,
    )

    await site.start()

    LOG.info(
        "Webサーバー起動: port=%s",
        port,
    )

    return runner


# =========================================================
# メイン起動処理
# =========================================================

async def main():

    if not TOKEN:

        raise RuntimeError(
            "環境変数 DISCORD_TOKEN が設定されていません。"
        )

    validate_config()

    web_runner = await start_web_server()

    try:

        async with bot:

            await bot.start(
                TOKEN
            )

    finally:

        await web_runner.cleanup()


# =========================================================
# 実行
# =========================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        LOG.info(
            "Botを停止しました。"
        )
