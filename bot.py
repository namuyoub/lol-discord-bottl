
# ============================================================
# Nexus BOT - 修正版
# Part 1 / 8 : 基本設定・共通機能
# ============================================================

import discord
from discord.ext import commands
from discord import app_commands

import asyncio
import logging
import os
import re
import unicodedata
from urllib.parse import quote
from typing import Optional

# ============================================================
# ログ設定
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("NexusBOT")

# ============================================================
# BOT設定
# ============================================================

BOT_TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = 1566019287473193063
OWNER_ID = 1392895521433321502

# ============================================================
# チャンネル設定
# ============================================================

REGISTRATION_CHANNEL_ID = 1566023396544745613
INPUT_CHECK_CHANNEL_ID = 1566055273146093599

FA_CARD_CHANNEL_ID = 1567091839519948840

TOURNAMENT_CHANNEL_ID = 1566061702716329994

TEAM_APPLICATION_CATEGORY_ID = 1566028466397384854

NORMAL_RECRUIT_CHANNEL_ID = 1569643108147265709
RANK_RECRUIT_CHANNEL_ID = 1569643437035229326
FLEX_RECRUIT_CHANNEL_ID = 1569643504999604285

CUSTOM_PANEL_CHANNEL_ID = 1567318455391101030

ROLE_PANEL_CHANNEL_ID = 1569616670035681353

# ============================================================
# ロール設定
# ============================================================

NORMAL_ROLE_ID = 1569579116750049380
CUSTOM_ROLE_ID = 1569578833953427507
TOURNAMENT_ROLE_ID = 1569578720216358923
RANK_ROLE_ID = 1569578957236473876

SELECTABLE_ROLE_IDS = [
    NORMAL_ROLE_ID,
    CUSTOM_ROLE_ID,
    TOURNAMENT_ROLE_ID,
    RANK_ROLE_ID,
]

# ============================================================
# 選手ランク設定（ポイント制廃止・ランク帯で統一）
# ============================================================

RANK_CHOICES = [
    "Challenger",
    "Grandmaster",
    "Master",
    "Diamond",
    "Emerald",
    "Platinum",
]

RANK_COLORS = {
    "Challenger": 0xE74C3C,
    "Grandmaster": 0x9B59B6,
    "Master": 0x3498DB,
    "Diamond": 0x00BFFF,
    "Emerald": 0x2ECC71,
    "Platinum": 0x48C9B0,
    "Coach": 0x95A5A6,
}

# ============================================================
# 希望ロール設定
# ============================================================

MAIN_ROLE_CHOICES = [
    "TOP",
    "JG",
    "MID",
    "ADC",
    "SUP",
]

# ============================================================
# 募集設定
# ============================================================

CUSTOM_RECRUIT_PER_LIST = 3

# ============================================================
# Embedカラー
# ============================================================

DEFAULT_COLOR = 0x5865F2
SUCCESS_COLOR = 0x2ECC71
ERROR_COLOR = 0xE74C3C
WARNING_COLOR = 0xF1C40F

# ============================================================
# 共通Embed作成
# ============================================================

def create_embed(
    title: str,
    description: str = "",
    color: int = DEFAULT_COLOR,
) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        color=color,
    )


def create_rank_embed(
    title: str,
    description: str,
    rank: str,
) -> discord.Embed:
    return create_embed(
        title,
        description,
        RANK_COLORS.get(rank, DEFAULT_COLOR),
    )


def success_embed(title: str, description: str = ""):
    return create_embed(
        f"✅ {title}",
        description,
        SUCCESS_COLOR,
    )


def error_embed(title: str, description: str = ""):
    return create_embed(
        f"❌ {title}",
        description,
        ERROR_COLOR,
    )


def warning_embed(title: str, description: str = ""):
    return create_embed(
        f"⚠️ {title}",
        description,
        WARNING_COLOR,
    )


# ============================================================
# 権限確認
# ============================================================

def is_owner(user: discord.abc.User) -> bool:
    return user.id == OWNER_ID


def can_manage_recruit(
    user: discord.abc.User,
    recruiter_id: int,
) -> bool:
    return user.id in (recruiter_id, OWNER_ID)

_HIDDEN_ID_PREFIX = "\u2063"
_HIDDEN_ID_ZERO = "\u200b"
_HIDDEN_ID_ONE = "\u200c"


def encode_hidden_user_id(user_id: int) -> str:
    return _HIDDEN_ID_PREFIX + "".join(
        _HIDDEN_ID_ONE if bit == "1" else _HIDDEN_ID_ZERO
        for bit in format(user_id, "064b")
    )


def decode_hidden_user_id(footer_text: str) -> Optional[int]:
    if footer_text.startswith(_HIDDEN_ID_PREFIX):
        encoded = footer_text[len(_HIDDEN_ID_PREFIX):]
        bits = "".join(
            "0" if char == _HIDDEN_ID_ZERO else "1"
            for char in encoded[:64]
            if char in (_HIDDEN_ID_ZERO, _HIDDEN_ID_ONE)
        )
        if len(bits) == 64:
            return int(bits, 2)
    match = re.search(r"Creator ID: (\d+)", footer_text)
    return int(match.group(1)) if match else None




def can_manage_participant(
    user: discord.abc.User,
    participant_id: int,
) -> bool:
    return user.id in (participant_id, OWNER_ID)


# ============================================================
# Riot ID・OP.GG関連
# ============================================================

def normalize_riot_id(riot_id: str) -> str:
    return unicodedata.normalize("NFKC", riot_id.strip())


def make_opgg_url(riot_id: str) -> Optional[str]:
    """
    Riot ID から OP.GG の URL を生成する。
    形式：プレイヤー名#タグ
    """

    riot_id = normalize_riot_id(riot_id)

    if "#" not in riot_id:
        return None

    game_name, tag_line = riot_id.rsplit("#", 1)

    game_name = game_name.strip()
    tag_line = tag_line.strip()

    if not game_name or not tag_line:
        return None

    region = "jp"
    encoded_name = quote(game_name, safe="")
    encoded_tag = quote(tag_line, safe="")

    return (
        f"https://www.op.gg/summoners/{region}/"
        f"{encoded_name}-{encoded_tag}"
    )


# ============================================================
# Discord BOT設定
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True


class NexusBot(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
        )

    async def setup_hook(self):

        logger.info("Nexus BOT 起動準備中")

        guild = discord.Object(id=GUILD_ID)

        # 古いグローバルコマンドを削除し、現在のコマンド定義は保持する
        global_commands = self.tree.get_commands()
        self.tree.clear_commands(guild=None)
        await self.tree.sync()
        for command in global_commands:
            self.tree.add_command(command)

        # このBOTを導入しているサーバーにだけコマンドを登録
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

        logger.info("スラッシュコマンド同期完了")

    async def on_ready(self):

        logger.info(f"ログイン成功: {self.user}")

        await self.change_presence(
            activity=discord.Game("Nexus Server")
        )


bot = NexusBot()

# ============================================================
# Part 1 終了
# 次は Part 2：選手登録機能
# ============================================================


# ============================================================
# Nexus BOT - Part 2 / 8
# 選手登録機能
# ============================================================

# 登録情報
# ※ Card発行機能でもこの情報を利用する
PLAYER_RECORDS = {}


# ============================================================
# 選手登録入力画面
# ============================================================

class RegistrationSelectView(discord.ui.View):

    def __init__(self, user_id: int, is_fa: bool = False):
        super().__init__(timeout=600)

        self.user_id = user_id
        self.is_fa = is_fa
        self.selected_rank = None
        self.selected_roles = []

        self.add_item(RegistrationRankSelect(self))
        self.add_item(RegistrationRoleSelect(self))

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "この登録画面は操作できません。",
                ephemeral=True,
            )
            return False

        return True

    @discord.ui.button(
        label="入力へ進む",
        style=discord.ButtonStyle.success,
        custom_id="registration:continue",
        row=2,
    )
    async def continue_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        if not self.selected_rank:
            await interaction.response.send_message(
                "先にランクを選択してください。",
                ephemeral=True,
            )
            return

        if not self.selected_roles:
            await interaction.response.send_message(
                "希望ロールを1つ以上選択してください。",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            RegistrationModal(self.selected_rank, self.selected_roles, is_fa=self.is_fa)
        )


# ============================================================
# ランク選択
# ============================================================

class RegistrationRankSelect(discord.ui.Select):

    def __init__(self, parent_view):

        self.parent_view = parent_view

        options = [
            discord.SelectOption(
                label=rank,
                value=rank,
            )
            for rank in RANK_CHOICES
        ]

        super().__init__(
            placeholder="希望ランクを選択してください",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):

        self.parent_view.selected_rank = self.values[0]

        await interaction.response.edit_message(
            content=(
                f"ランク：**{self.parent_view.selected_rank}**\n"
                f"希望ロール："
                f"{'・'.join(self.parent_view.selected_roles) or '未選択'}\n\n"
                "希望ロールは複数選択可能です。\n"
                "選択が終わったら「入力へ進む」を押してください。"
            ),
            view=self.parent_view,
        )


# ============================================================
# 希望ロール選択（複数選択可能）
# ============================================================

class RegistrationRoleSelect(discord.ui.Select):

    def __init__(self, parent_view):

        self.parent_view = parent_view

        options = [
            discord.SelectOption(
                label=role,
                value=role,
            )
            for role in MAIN_ROLE_CHOICES
        ]

        super().__init__(
            placeholder="希望ロールを選択（複数選択可能）",
            min_values=1,
            max_values=5,
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):

        self.parent_view.selected_roles = self.values

        await interaction.response.edit_message(
            content=(
                f"ランク："
                f"**{self.parent_view.selected_rank or '未選択'}**\n"
                f"希望ロール："
                f"**{'・'.join(self.parent_view.selected_roles)}**\n\n"
                "希望ロールは複数選択可能です。\n"
                "選択が終わったら「入力へ進む」を押してください。"
            ),
            view=self.parent_view,
        )


# ============================================================
# Riot ID・自己PR入力画面
# ============================================================

class RegistrationModal(discord.ui.Modal):

    def __init__(self, rank: str, roles: list, is_fa: bool = False):
        super().__init__(title="FA Card作成" if is_fa else "選手登録", timeout=600)
        self.rank = rank
        self.roles = roles
        self.is_fa = is_fa

        self.riot_id = discord.ui.TextInput(
            label="Riot ID（名前#TAG）",
            placeholder="例：Player#JP1",
            max_length=64,
            required=True,
        )

        self.self_pr = discord.ui.TextInput(
            label="自己PR",
            placeholder="得意なことや活動時間などを入力してください",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )

        self.add_item(self.riot_id)
        self.add_item(self.self_pr)

    async def on_submit(self, interaction: discord.Interaction):

        riot_id = normalize_riot_id(str(self.riot_id.value))

        if make_opgg_url(riot_id) is None:
            await interaction.response.send_message(
                "Riot IDの形式が正しくありません。\n"
                "「名前#TAG」の形式で入力してください。",
                ephemeral=True,
            )
            return

        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "サーバー内で操作してください。",
                ephemeral=True,
            )
            return

        game_name = riot_id.rsplit("#", 1)[0].strip()
        roles_text = "・".join(self.roles)

        if self.is_fa:
            opgg_url = make_opgg_url(riot_id)
            embed = create_rank_embed(
                "Nexus League | FREE AGENT",
                f"## {game_name}\n**{self.rank}**\n希望ロール：**{roles_text}**",
                self.rank,
            )
            embed.add_field(name="RANK", value=f"**{self.rank}**", inline=True)
            embed.add_field(name="RIOT ID", value=f"`{riot_id}`", inline=True)
            embed.add_field(name="SELF PR", value=str(self.self_pr.value).strip()[:1000] or "未記入", inline=False)
            embed.add_field(name="OP.GG", value=f"[プロフィールを確認する]({opgg_url})", inline=False)
            embed.set_footer(text="Nexus League | Free Agent")
            channel = guild.get_channel(FA_CARD_CHANNEL_ID)
            if channel is None:
                try:
                    channel = await bot.fetch_channel(FA_CARD_CHANNEL_ID)
                except discord.HTTPException:
                    channel = None
            if channel is None:
                await interaction.response.send_message("FA Cardチャンネルが見つかりません。", ephemeral=True)
                return
            try:
                await channel.send(embed=embed, view=OPggLinkView(opgg_url))
            except discord.Forbidden:
                await interaction.response.send_message("FA Cardチャンネルへの送信権限がありません。", ephemeral=True)
                return
            except discord.HTTPException:
                await interaction.response.send_message("FA Cardの発行に失敗しました。", ephemeral=True)
                return
            await interaction.response.send_message("FA Cardを発行しました！", ephemeral=True)
            return

        # Discordのニックネームは最大32文字
        nickname = (
            f"{game_name} / {roles_text} / {self.rank}"
        )[:32]

        nickname_result = "変更成功"

        try:
            await interaction.user.edit(
                nick=nickname,
                reason="Nexus選手登録",
            )
        except discord.Forbidden:
            nickname_result = "変更できませんでした（権限不足）"
        except discord.HTTPException:
            nickname_result = "変更できませんでした"

        # Card発行機能で参照する登録情報
        PLAYER_RECORDS[interaction.user.id] = {
            "user_id": interaction.user.id,
            "discord_name": str(interaction.user),
            "riot_id": riot_id,
            "game_name": game_name,
            "rank": self.rank,
             "roles": list(self.roles),
            "self_pr": str(self.self_pr.value),
        }

        embed = create_rank_embed(
            "選手登録申請",
            "新しい選手登録が届きました。",
            self.rank,
        )

        embed.add_field(
            name="プレイヤー",
            value=game_name,
            inline=True,
        )

        embed.add_field(
            name="Riot ID",
            value=riot_id,
            inline=True,
        )

        embed.add_field(
            name="ランク",
            value=self.rank,
            inline=True,
        )

        embed.add_field(
            name="希望ロール",
            value=roles_text,
            inline=True,
        )

        embed.add_field(
            name="自己PR",
            value=str(self.self_pr.value)[:1000],
            inline=False,
        )

        embed.add_field(
            name="申請者",
            value=interaction.user.mention,
            inline=False,
        )

        embed.set_footer(
            text=f"Discord ID: {interaction.user.id}"
        )

        check_channel = guild.get_channel(
            INPUT_CHECK_CHANNEL_ID
        )

        if check_channel is None:
            try:
                check_channel = await bot.fetch_channel(
                    INPUT_CHECK_CHANNEL_ID
                )
            except discord.HTTPException:
                check_channel = None

        if check_channel is None:
            await interaction.response.send_message(
                "登録情報は受け取りましたが、"
                "確認用チャンネルが見つかりません。\n"
                "運営者に連絡してください。",
                ephemeral=True,
            )
            return

        try:
            await check_channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                "確認用チャンネルへの送信権限がありません。",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "選手登録を受け付けました！\n"
            f"ニックネーム：`{nickname}`\n"
            f"ニックネーム変更：{nickname_result}",
            ephemeral=True,
        )


# ============================================================
# 登録パネル（再起動後もボタンを維持）
# ============================================================

class RegistrationStartView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="選手登録",
        style=discord.ButtonStyle.primary,
        emoji="📝",
        custom_id="nexus:registration:start",
    )
    async def start_registration(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        view = RegistrationSelectView(
            interaction.user.id
        )

        await interaction.response.send_message(
            "### 選手登録\n"
            "ランクと希望ロールを選択してください。\n"
            "希望ロールは複数選択可能です。",
            view=view,
            ephemeral=True,
        )


# ============================================================
# 選手登録パネル設置コマンド
# ============================================================

@bot.tree.command(
    name="setup_registration",
    description="選手登録パネルを設置します",
)
async def setup_registration(
    interaction: discord.Interaction,
):

    if not is_owner(interaction.user):
        await interaction.response.send_message(
            "このコマンドは運営者専用です。",
            ephemeral=True,
        )
        return

    channel = interaction.guild.get_channel(
        REGISTRATION_CHANNEL_ID
    )

    if channel is None:
        await interaction.response.send_message(
            "選手登録チャンネルが見つかりません。",
            ephemeral=True,
        )
        return

    embed = create_embed(
        "Nexus League | 選手登録",
        (
            "Nexus Leagueへの選手登録はこちらから行えます。\n\n"
            "**登録内容**\n"
            "・Riot ID（名前#TAG）\n"
            "・ランク\n"
            "・希望ロール（複数選択可能）\n"
            "・自己PR\n\n"
            "Riot IDからOP.GGのURLはBOTが自動生成します。"
        ),
    )

    await channel.send(
        embed=embed,
        view=RegistrationStartView(),
    )

    await interaction.response.send_message(
        "選手登録パネルを設置しました。",
        ephemeral=True,
    )


# ============================================================
# Part 2 終了
# ============================================================


# ============================================================
# Nexus BOT - Part 3 / 8
# FA Card発行機能
# ============================================================

# ============================================================
# FA Card用 OP.GGリンクボタン
# ============================================================

class OPggLinkView(discord.ui.View):

    def __init__(self, opgg_url: str):
        super().__init__(timeout=None)

        self.add_item(
            discord.ui.Button(
                label="OP.GGを開く",
                style=discord.ButtonStyle.link,
                url=opgg_url,
                emoji="🔎",
            )
        )


# ============================================================
# FA Card発行コマンド
# ============================================================

@bot.tree.command(
    name="fa_card",
    description="FA Cardを作成します",
)
async def fa_card(interaction: discord.Interaction):
    if not is_owner(interaction.user):
        await interaction.response.send_message("このコマンドは運営者専用です。", ephemeral=True)
        return
    view = RegistrationSelectView(interaction.user.id, is_fa=True)
    await interaction.response.send_message(
        "### FA Card作成\nランクと希望ロールを選択してください。\n希望ロールは複数選択できます。",
        view=view,
        ephemeral=True,
    )


# Part 3 終了
# ============================================================


# ============================================================
# Nexus BOT - Part 4 / 8
# 大会募集機能
# ============================================================

TOURNAMENT_PARTICIPANTS_FIELD = "参加チーム"


# ============================================================
# 参加チーム一覧の取得
# ============================================================

def get_tournament_participants(embed: discord.Embed):
    for field in embed.fields:
        if field.name == TOURNAMENT_PARTICIPANTS_FIELD:
            if field.value == "まだ参加チームはいません":
                return []

            return [
                line.strip()
                for line in field.value.splitlines()
                if line.strip()
            ]

    return []


# ============================================================
# 参加チーム一覧の更新
# ============================================================

def update_tournament_participants(
    embed: discord.Embed,
    participants: list[str],
):
    value = (
        "\n".join(participants)
        if participants
        else "まだ参加チームはいません"
    )

    value = value[:1024]

    for index, field in enumerate(embed.fields):
        if field.name == TOURNAMENT_PARTICIPANTS_FIELD:
            embed.set_field_at(
                index,
                name=TOURNAMENT_PARTICIPANTS_FIELD,
                value=value,
                inline=False,
            )
            return

    embed.add_field(
        name=TOURNAMENT_PARTICIPANTS_FIELD,
        value=value,
        inline=False,
    )


# ============================================================
# 大会募集メッセージ取得
# ============================================================

async def fetch_tournament_message(
    interaction: discord.Interaction,
    channel_id: int,
    message_id: int,
):
    try:
        channel = await interaction.client.fetch_channel(
            channel_id
        )

        message = await channel.fetch_message(
            message_id
        )

        return message

    except (discord.HTTPException, AttributeError):
        return None


# ============================================================
# 大会参加モーダル
# ============================================================

class TournamentJoinModal(discord.ui.Modal):

    def __init__(
        self,
        channel_id: int,
        message_id: int,
    ):
        super().__init__(title="大会に参加する")

        self.channel_id = channel_id
        self.message_id = message_id

        self.team_name = discord.ui.TextInput(
            label="チーム名",
            placeholder="チーム名を入力してください",
            max_length=80,
            required=True,
        )

        self.add_item(self.team_name)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):
        message = await fetch_tournament_message(
            interaction,
            self.channel_id,
            self.message_id,
        )

        if message is None or not message.embeds:
            await interaction.response.send_message(
                "大会募集を取得できませんでした。",
                ephemeral=True,
            )
            return

        embed = message.embeds[0].copy()

        if "募集終了" in embed.title:
            await interaction.response.send_message(
                "この大会募集は終了しています。",
                ephemeral=True,
            )
            return

        team_name = self.team_name.value.strip()

        if not team_name:
            await interaction.response.send_message(
                "チーム名を入力してください。",
                ephemeral=True,
            )
            return

        participants = get_tournament_participants(embed)

        # 同じチーム名の重複確認
        if any(
            line.split(" | ", 1)[0].casefold()
            == team_name.casefold()
            and f"<@{interaction.user.id}>" not in line
            for line in participants
        ):
            await interaction.response.send_message(
                "そのチーム名はすでに登録されています。",
                ephemeral=True,
            )
            return

        # 同じユーザーの以前の登録を削除
        participants = [
            line
            for line in participants
            if f"<@{interaction.user.id}>" not in line
        ]

        # 新しい参加情報を登録
        participants.append(
            f"{team_name} | <@{interaction.user.id}>"
        )

        update_tournament_participants(
            embed,
            participants,
        )

        await message.edit(embed=embed)

        await interaction.response.send_message(
            f"チーム **{team_name}** で参加登録しました！",
            ephemeral=True,
        )


# ============================================================
# 大会辞退モーダル
# ============================================================

class TournamentDeclineModal(discord.ui.Modal):

    def __init__(
        self,
        channel_id: int,
        message_id: int,
    ):
        super().__init__(title="大会参加を辞退する")

        self.channel_id = channel_id
        self.message_id = message_id

        self.team_name = discord.ui.TextInput(
            label="辞退するチーム名",
            placeholder="登録したチーム名を正確に入力",
            max_length=80,
            required=True,
        )

        self.add_item(self.team_name)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):
        message = await fetch_tournament_message(
            interaction,
            self.channel_id,
            self.message_id,
        )

        if message is None or not message.embeds:
            await interaction.response.send_message(
                "大会募集を取得できませんでした。",
                ephemeral=True,
            )
            return

        embed = message.embeds[0].copy()

        if "募集終了" in embed.title:
            await interaction.response.send_message(
                "この大会募集は終了しています。",
                ephemeral=True,
            )
            return

        team_name = self.team_name.value.strip()
        participants = get_tournament_participants(embed)

        target = None

        for line in participants:
            parts = line.split(" | ", 1)

            if len(parts) != 2:
                continue

            saved_team_name, member_text = parts

            if saved_team_name.casefold() == team_name.casefold():

                # 運営者以外は自分の登録だけ辞退可能
                if (
                    is_owner(interaction.user)
                    or f"<@{interaction.user.id}>" in member_text
                ):
                    target = line

                break

        if target is None:
            await interaction.response.send_message(
                "該当するチームがないか、辞退する権限がありません。",
                ephemeral=True,
            )
            return

        participants.remove(target)

        update_tournament_participants(
            embed,
            participants,
        )

        await message.edit(embed=embed)

        await interaction.response.send_message(
            f"チーム **{team_name}** の参加を取り消しました。",
            ephemeral=True,
        )


# ============================================================
# 大会募集ボタン
# ============================================================

class TournamentView(discord.ui.View):

    def __init__(self, disabled: bool = False):
        super().__init__(timeout=None)

        join_button = discord.ui.Button(
            label="参加する",
            style=discord.ButtonStyle.success,
            emoji="✅",
            custom_id="nexus:tournament:join",
            disabled=disabled,
        )

        decline_button = discord.ui.Button(
            label="辞退する",
            style=discord.ButtonStyle.secondary,
            emoji="↩️",
            custom_id="nexus:tournament:decline",
            disabled=disabled,
        )

        end_button = discord.ui.Button(
            label="募集を終了する",
            style=discord.ButtonStyle.danger,
            emoji="🔒",
            custom_id="nexus:tournament:end",
            disabled=disabled,
        )

        join_button.callback = self.join_callback
        decline_button.callback = self.decline_callback
        end_button.callback = self.end_callback

        self.add_item(join_button)
        self.add_item(decline_button)
        self.add_item(end_button)

    async def join_callback(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_modal(
            TournamentJoinModal(
                interaction.channel_id,
                interaction.message.id,
            )
        )

    async def decline_callback(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_modal(
            TournamentDeclineModal(
                interaction.channel_id,
                interaction.message.id,
            )
        )

    async def end_callback(
        self,
        interaction: discord.Interaction,
    ):
        message = interaction.message

        if not message or not message.embeds:
            await interaction.response.send_message(
                "大会募集を取得できませんでした。",
                ephemeral=True,
            )
            return

        embed = message.embeds[0].copy()

        footer_text = embed.footer.text or ""
        creator_id = decode_hidden_user_id(footer_text)

        if not can_manage_recruit(
            interaction.user,
            creator_id,
        ):
            await interaction.response.send_message(
                "募集を終了できるのは作成者または運営者だけです。",
                ephemeral=True,
            )
            return

        if "募集終了" in embed.title:
            await interaction.response.send_message(
                "この募集はすでに終了しています。",
                ephemeral=True,
            )
            return

        embed.title = f"【募集終了】{embed.title}"
        embed.color = discord.Color.dark_grey()

        embed.add_field(
            name="状態",
            value="この大会募集は終了しました。",
            inline=False,
        )

        await message.edit(
            embed=embed,
            view=TournamentView(disabled=True),
        )

        await interaction.response.send_message(
            "大会募集を終了しました。",
            ephemeral=True,
        )


# ============================================================
# 大会募集作成モーダル
# ============================================================

class TournamentCreateModal(discord.ui.Modal):

    def __init__(self):
        super().__init__(title="大会募集を作成")

        self.tournament_name = discord.ui.TextInput(
            label="大会名",
            placeholder="例：Nexus Cup",
            max_length=100,
            required=True,
        )

        self.event_datetime = discord.ui.TextInput(
            label="開催日時",
            placeholder="例：2026/12/20 20:00",
            max_length=100,
            required=True,
        )

        self.deadline = discord.ui.TextInput(
            label="参加締切",
            placeholder="例：2026/12/18 23:59",
            max_length=100,
            required=True,
        )

        self.details = discord.ui.TextInput(
            label="大会詳細",
            placeholder="ルール・参加条件など",
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=True,
        )

        self.add_item(self.tournament_name)
        self.add_item(self.event_datetime)
        self.add_item(self.deadline)
        self.add_item(self.details)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):
        channel = (
            interaction.guild.get_channel(
                TOURNAMENT_CHANNEL_ID
            )
            if interaction.guild
            else None
        )

        if channel is None:
            try:
                channel = await bot.fetch_channel(
                    TOURNAMENT_CHANNEL_ID
                )
            except discord.HTTPException:
                channel = None

        if channel is None:
            await interaction.response.send_message(
                "大会募集チャンネルが見つかりません。",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"🏆 {self.tournament_name.value.strip()}",
            description=self.details.value.strip(),
            color=discord.Color.gold(),
        )

        embed.add_field(
            name="開催日時",
            value=self.event_datetime.value.strip(),
            inline=True,
        )

        embed.add_field(
            name="参加締切",
            value=self.deadline.value.strip(),
            inline=True,
        )

        update_tournament_participants(
            embed,
            [],
        )

        embed.set_footer(text=encode_hidden_user_id(interaction.user.id))

        try:
            await channel.send(
                content=(
                    "<@&1569578720216358923> "
                    "大会参加者を募集します！"
                ),
                embed=embed,
                view=TournamentView(),
                allowed_mentions=discord.AllowedMentions(
                    roles=True
                ),
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "大会募集チャンネルへの送信権限がありません。",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            await interaction.response.send_message(
                "大会募集の作成に失敗しました。",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "大会募集を作成しました！",
            ephemeral=True,
        )


# ============================================================
# 大会募集作成コマンド
# ============================================================

@bot.tree.command(
    name="tournament_create",
    description="大会参加者の募集を作成します",
)
async def tournament_create(
    interaction: discord.Interaction,
):

    if not is_owner(interaction.user):
        await interaction.response.send_message(
            "このコマンドは運営者専用です。",
            ephemeral=True,
        )
        return

    await interaction.response.send_modal(
        TournamentCreateModal()
    )


# ============================================================
# Part 4 終了
# ============================================================


# ============================================================
# Nexus BOT - Part 5 / 8
# チーム専用チャンネル機能
# ============================================================

# ============================================================
# 非公開チャンネル作成（チーム結成・チーム解散）
# ============================================================

async def create_private_team_channel(
    interaction: discord.Interaction,
    channel_name: str,
    channel_type: str,
):
    guild = interaction.guild

    if guild is None:
        await interaction.response.send_message(
            "サーバー内で使用してください。",
            ephemeral=True,
        )
        return

    # 同じ本人が同じ用途のチャンネルを既に作っていないか確認
    for channel in guild.text_channels:
        topic = channel.topic or ""
        if (
            f"Team Owner ID: {interaction.user.id}" in topic
            and f"Team Type: {channel_type}" in topic
        ):
            await interaction.response.send_message(
                f"すでに作成されています：{channel.mention}",
                ephemeral=True,
            )
            return

    bot_member = guild.me
    if bot_member is None and bot.user is not None:
        bot_member = guild.get_member(bot.user.id)

    if bot_member is None:
        await interaction.response.send_message(
            "BOTのサーバー情報を取得できませんでした。",
            ephemeral=True,
        )
        return

    operator = guild.get_member(OWNER_ID)
    if operator is None:
        try:
            operator = await guild.fetch_member(OWNER_ID)
        except discord.HTTPException:
            operator = None

    if operator is None:
        await interaction.response.send_message(
            "運営者をサーバー内で確認できませんでした。運営者の参加状態を確認してください。",
            ephemeral=True,
        )
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False,
        ),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
        ),
        operator: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
        ),
        bot_member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True,
        ),
    }

    try:
        new_channel = await guild.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            topic=(
                f"Team Owner ID: {interaction.user.id} | "
                f"Team Type: {channel_type}"
            ),
            reason=f"{channel_name} 非公開チャンネル作成：{interaction.user}",
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "BOTにチャンネル作成権限がありません。",
            ephemeral=True,
        )
        return
    except discord.HTTPException as error:
        await interaction.response.send_message(
            f"非公開チャンネルの作成に失敗しました。\n詳細：{error}",
            ephemeral=True,
        )
        return

    await new_channel.send(
        f"{interaction.user.mention} さんと運営者だけが閲覧できるチャンネルです。"
    )
    await interaction.response.send_message(
        f"非公開チャンネル **{channel_name}** を作成しました！\n{new_channel.mention}",
        ephemeral=True,
    )


# ============================================================
# チーム結成チャンネル作成ボタン
# ============================================================

class TeamCreateButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="チーム結成",
            style=discord.ButtonStyle.success,
            emoji="➕",
            custom_id="nexus:team:create",
        )

    async def callback(self, interaction: discord.Interaction):
        await create_private_team_channel(
            interaction,
            "チーム結成",
            "create",
        )


# ============================================================
# チーム解散チャンネル作成ボタン
# ※チャンネルを削除する機能ではありません
# ============================================================

class TeamDeleteButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="チーム解散",
            style=discord.ButtonStyle.danger,
            emoji="📝",
            custom_id="nexus:team:delete",
        )

    async def callback(self, interaction: discord.Interaction):
        await create_private_team_channel(
            interaction,
            "チーム解散",
            "disband",
        )


# ============================================================
# 非公開チャンネル作成パネル
# ============================================================

class TeamApplicationPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TeamCreateButton())
        self.add_item(TeamDeleteButton())


# ============================================================
# 専用チャンネルパネル設置コマンド
# ============================================================

@bot.tree.command(
    name="setup_team_panel",
    description="チーム専用チャンネルのパネルを設置します",
)
async def setup_team_panel(
    interaction: discord.Interaction,
):

    if not is_owner(interaction.user):
        await interaction.response.send_message(
            "このコマンドは運営者専用です。",
            ephemeral=True,
        )
        return

    if interaction.guild is None:
        await interaction.response.send_message(
            "サーバー内で使用してください。",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="チーム申請・専用チャンネル",
        description=(
            "用途に合わせてボタンを押すと、非公開チャンネルを作成します。\n\n"
            "➕ **チーム結成**\n"
            "チーム結成について相談するチャンネルを作成します。\n\n"
            "📝 **チーム解散**\n"
            "チーム解散について相談するチャンネルを作成します。\n\n"
            "※作成した本人と運営者だけが閲覧できます。\n"
            "※ボタンを押しても既存チャンネルは削除されません。"
        ),
        color=discord.Color.blurple(),
    )

    try:
        await interaction.channel.send(
            embed=embed,
            view=TeamApplicationPanelView(),
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "このチャンネルに投稿する権限がありません。",
            ephemeral=True,
        )
        return
    except discord.HTTPException:
        await interaction.response.send_message(
            "パネルの設置に失敗しました。",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        "チーム申請パネルを設置しました！",
        ephemeral=True,
    )


# ============================================================
# Part 5 終了
# ============================================================


# ============================================================
# Nexus BOT - Part 6 / 8
# 通常・ランク・Flex募集機能
# ============================================================

RECRUIT_CHANNEL_SETTINGS = {
    NORMAL_RECRUIT_CHANNEL_ID: {
        "name": "通常募集",
        "role_id": NORMAL_ROLE_ID,
    },
    RANK_RECRUIT_CHANNEL_ID: {
        "name": "ランク募集",
        "role_id": RANK_ROLE_ID,
    },
    FLEX_RECRUIT_CHANNEL_ID: {
        "name": "Flex募集",
        "role_id": RANK_ROLE_ID,
    },
}


# ============================================================
# 募集Embedの参加者一覧を取得
# ============================================================

def get_recruit_members(
    embed: discord.Embed,
    field_name: str,
):
    for field in embed.fields:
        if field.name == field_name:
            if field.value == "まだいません":
                return []

            return [
                line.strip()
                for line in field.value.splitlines()
                if line.strip()
            ]

    return []


# ============================================================
# 募集Embedの参加者一覧を更新
# ============================================================

def set_recruit_members(
    embed: discord.Embed,
    field_name: str,
    members: list[str],
):
    value = "\n".join(members) if members else "まだいません"
    value = value[:1024]

    for index, field in enumerate(embed.fields):
        if field.name == field_name:
            embed.set_field_at(
                index,
                name=field_name,
                value=value,
                inline=False,
            )
            return

    embed.add_field(
        name=field_name,
        value=value,
        inline=False,
    )


# ============================================================
# 募集ボタン
# ============================================================

class RecruitmentView(discord.ui.View):

    def __init__(self, disabled: bool = False):
        super().__init__(timeout=None)

        join_button = discord.ui.Button(
            label="参加",
            emoji="🙋",
            style=discord.ButtonStyle.success,
            custom_id="nexus:recruit:join",
            disabled=disabled,
        )

        late_button = discord.ui.Button(
            label="途中参加",
            emoji="⏰",
            style=discord.ButtonStyle.primary,
            custom_id="nexus:recruit:late",
            disabled=disabled,
        )

        decline_button = discord.ui.Button(
            label="辞退する",
            emoji="↩️",
            style=discord.ButtonStyle.secondary,
            custom_id="nexus:recruit:decline",
            disabled=disabled,
        )

        end_button = discord.ui.Button(
            label="募集を終了する",
            emoji="🔒",
            style=discord.ButtonStyle.danger,
            custom_id="nexus:recruit:end",
            disabled=disabled,
        )

        join_button.callback = self.join_callback
        late_button.callback = self.late_callback
        decline_button.callback = self.decline_callback
        end_button.callback = self.end_callback

        self.add_item(join_button)
        self.add_item(late_button)
        self.add_item(decline_button)
        self.add_item(end_button)

    def get_creator_id(self, message: discord.Message):
        if not message.embeds:
            return None

        footer = message.embeds[0].footer.text or ""

        match = re.search(
            r"Creator ID: (\d+)",
            footer,
        )

        return int(match.group(1)) if match else None

    async def update_member(
        self,
        interaction: discord.Interaction,
        action: str,
    ):
        # Discordの3秒応答期限対策：編集処理より先にACKする
        await interaction.response.defer(ephemeral=True)

        message = interaction.message

        if message is None or not message.embeds:
            await interaction.followup.send(
                "募集情報を取得できませんでした。",
                ephemeral=True,
            )
            return

        embed = message.embeds[0].copy()

        if "募集終了" in embed.title:
            await interaction.followup.send(
                "この募集は終了しています。",
                ephemeral=True,
            )
            return

        joined = get_recruit_members(embed, "参加者")
        late = get_recruit_members(embed, "途中参加")

        user_mention = interaction.user.mention
        user_id_text = f"<@{interaction.user.id}>"

        # 既存の参加状態をすべて解除
        joined = [
            item for item in joined
            if item != user_id_text
        ]
        late = [
            item for item in late
            if item != user_id_text
        ]

        if action == "join":
            joined.append(user_id_text)
            reply = f"{user_mention} さんが参加してくれるよ！"

        elif action == "late":
            late.append(user_id_text)
            reply = f"{user_mention} さんが途中から参加するよ〜"

        else:
            reply = f"{user_mention} さんが辞退したからね〜"

        set_recruit_members(
            embed,
            "参加者",
            joined,
        )

        set_recruit_members(
            embed,
            "途中参加",
            late,
        )

        await message.edit(embed=embed)
        thread = None
        reference = message.reference
        if reference and reference.message_id:
            try:
                parent_message = await message.channel.fetch_message(reference.message_id)
                thread = parent_message.thread
                if thread is not None and thread.archived:
                    await thread.edit(archived=False)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                thread = None
        if thread is not None:
            try:
                notice = ("参加してくれるよ！" if action == "join"
                          else "途中から参加するよ〜" if action == "late"
                          else "辞退したからね〜")
                await thread.send(
                    f"{interaction.user.mention} さんが{notice}",
                    allowed_mentions=discord.AllowedMentions(users=True),
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
        await interaction.response.send_message("参加状況を更新しました。", ephemeral=True)

    async def join_callback(
        self,
        interaction: discord.Interaction,
    ):
        await self.update_member(interaction, "join")

    async def late_callback(
        self,
        interaction: discord.Interaction,
    ):
        await self.update_member(interaction, "late")

    async def decline_callback(
        self,
        interaction: discord.Interaction,
    ):
        await self.update_member(interaction, "decline")

    async def end_callback(
        self,
        interaction: discord.Interaction,
    ):
        message = interaction.message

        if message is None or not message.embeds:
            await interaction.response.send_message(
                "募集情報を取得できませんでした。",
                ephemeral=True,
            )
            return

        embed = message.embeds[0].copy()
        creator_id = self.get_creator_id(message)

        if creator_id is None:
            await interaction.response.send_message(
                "募集作成者を確認できません。",
                ephemeral=True,
            )
            return

        if not can_manage_recruit(
            interaction.user,
            creator_id,
        ):
            await interaction.response.send_message(
                "募集を終了できるのは作成者または運営者だけです。",
                ephemeral=True,
            )
            return

        if "募集終了" in embed.title:
            await interaction.response.send_message(
                "この募集はすでに終了しています。",
                ephemeral=True,
            )
            return

        embed.title = f"【募集終了】{embed.title}"
        embed.color = discord.Color.dark_grey()

        embed.add_field(
            name="状態",
            value="この募集は終了しました。",
            inline=False,
        )

        await interaction.response.edit_message(
            embed=embed,
            view=RecruitmentView(disabled=True),
        )


# ============================================================
# 通常・ランク・Flex募集の自動作成
# ============================================================

@bot.listen("on_message")
async def create_recruitment_from_message(
    message: discord.Message,
):
    # BOT自身の投稿は無視
    if message.author.bot:
        return

    # 対象チャンネル以外は無視
    settings = RECRUIT_CHANNEL_SETTINGS.get(
        message.channel.id
    )

    if settings is None:
        return

    # サーバー外では処理しない
    if message.guild is None:
        return

    recruit_name = settings["name"]
    role_id = settings["role_id"]

    # 元投稿からスレッドを作成
    thread = None

    try:
        thread = await message.create_thread(
            name=f"{recruit_name} - {message.author.display_name}"[:100],
            auto_archive_duration=1440,
            reason="募集投稿の会話用スレッド",
        )

    except discord.HTTPException:
        logger.warning(
            "募集スレッドを作成できませんでした: %s",
            message.id,
        )

    # 募集Embedを作成
    embed = discord.Embed(
        title=f"🎮 {recruit_name}",
        description=(
            f"募集主：{message.author.mention}\n\n"
            "元の投稿に対する募集ボタンです。\n"
            "会話は作成されたスレッドをご利用ください。"
        ),
        color=discord.Color.blurple(),
    )

    if message.content:
        embed.add_field(
            name="募集内容",
            value=message.content[:1000],
            inline=False,
        )

    if thread is not None:
        embed.add_field(
            name="会話用スレッド",
            value=thread.mention,
            inline=False,
        )

    set_recruit_members(
        embed,
        "参加者",
        [],
    )

    set_recruit_members(
        embed,
        "途中参加",
        [],
    )

    embed.set_footer(
        text=f"Creator ID: {message.author.id}"
    )

    # 元投稿の直下にBotの返信としてボタンを設置
    try:
        await message.reply(
            content=(
                f"<@&{role_id}> "
                f"{message.author.mention} さんが立ち上げました！"
            ),
            embed=embed,
            view=RecruitmentView(),
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=True,
            ),
            mention_author=False,
        )

    except discord.HTTPException:
        logger.exception(
            "募集案内を送信できませんでした: %s",
            message.id,
        )


# ============================================================
# Part 6 終了
# ============================================================


# ============================================================
# Nexus BOT - Part 7 / 8
# カスタム募集機能
# ============================================================

# ============================================================
# カスタム募集の参加者一覧
# ============================================================

def get_custom_members(
    embed: discord.Embed,
    field_name: str,
):
    for field in embed.fields:
        if field.name == field_name:
            if field.value == "まだいません":
                return []

            return [
                line.strip()
                for line in field.value.splitlines()
                if line.strip()
            ]

    return []


def set_custom_members(
    embed: discord.Embed,
    field_name: str,
    members: list[str],
):
    value = (
        "\n".join(members)
        if members
        else "まだいません"
    )

    value = value[:1024]

    for index, field in enumerate(embed.fields):
        if field.name == field_name:
            embed.set_field_at(
                index,
                name=field_name,
                value=value,
                inline=False,
            )
            return

    embed.add_field(
        name=field_name,
        value=value,
        inline=False,
    )


# ============================================================
# カスタム募集ボタン
# ============================================================

class CustomRecruitmentView(discord.ui.View):

    def __init__(self, disabled: bool = False):
        super().__init__(timeout=None)

        join_button = discord.ui.Button(
            label="参加",
            emoji="🙋",
            style=discord.ButtonStyle.success,
            custom_id="nexus:custom:join",
            disabled=disabled,
        )

        late_button = discord.ui.Button(
            label="途中参加",
            emoji="⏰",
            style=discord.ButtonStyle.primary,
            custom_id="nexus:custom:late",
            disabled=disabled,
        )

        decline_button = discord.ui.Button(
            label="辞退する",
            emoji="↩️",
            style=discord.ButtonStyle.secondary,
            custom_id="nexus:custom:decline",
            disabled=disabled,
        )

        end_button = discord.ui.Button(
            label="募集を終了する",
            emoji="🔒",
            style=discord.ButtonStyle.danger,
            custom_id="nexus:custom:end",
            disabled=disabled,
        )

        join_button.callback = self.join_callback
        late_button.callback = self.late_callback
        decline_button.callback = self.decline_callback
        end_button.callback = self.end_callback

        self.add_item(join_button)
        self.add_item(late_button)
        self.add_item(decline_button)
        self.add_item(end_button)

    async def update_member(
        self,
        interaction: discord.Interaction,
        action: str,
    ):
        message = interaction.message

        if message is None or not message.embeds:
            await interaction.response.send_message(
                "募集情報を取得できませんでした。",
                ephemeral=True,
            )
            return

        embed = message.embeds[0].copy()

        if "募集終了" in embed.title:
            await interaction.response.send_message(
                "この募集は終了しています。",
                ephemeral=True,
            )
            return

        joined = get_custom_members(
            embed,
            "参加者",
        )

        late = get_custom_members(
            embed,
            "途中参加",
        )

        user_id_text = f"<@{interaction.user.id}>"

        # 既存の参加状態を解除
        joined = [
            item for item in joined
            if item != user_id_text
        ]

        late = [
            item for item in late
            if item != user_id_text
        ]

        if action == "join":
            joined.append(user_id_text)
        elif action == "late":
            late.append(user_id_text)

        set_custom_members(
            embed,
            "参加者",
            joined,
        )

        set_custom_members(
            embed,
            "途中参加",
            late,
        )

        await message.edit(embed=embed)

        await interaction.followup.send(
            "参加状況を更新しました。",
            ephemeral=True,
        )

    async def join_callback(
        self,
        interaction: discord.Interaction,
    ):
        await self.update_member(
            interaction,
            "join",
        )

    async def late_callback(
        self,
        interaction: discord.Interaction,
    ):
        await self.update_member(
            interaction,
            "late",
        )

    async def decline_callback(
        self,
        interaction: discord.Interaction,
    ):
        await self.update_member(
            interaction,
            "decline",
        )

    async def end_callback(
        self,
        interaction: discord.Interaction,
    ):
        message = interaction.message

        if message is None or not message.embeds:
            await interaction.response.send_message(
                "募集情報を取得できませんでした。",
                ephemeral=True,
            )
            return

        embed = message.embeds[0].copy()
        footer_text = embed.footer.text or ""
        creator_id = decode_hidden_user_id(footer_text)

        if not can_manage_recruit(
            interaction.user,
            creator_id,
        ):
            await interaction.response.send_message(
                "募集を終了できるのは作成者または運営者だけです。",
                ephemeral=True,
            )
            return

        if "募集終了" in embed.title:
            await interaction.response.send_message(
                "この募集はすでに終了しています。",
                ephemeral=True,
            )
            return

        embed.title = f"【募集終了】{embed.title}"
        embed.color = discord.Color.dark_grey()

        embed.add_field(
            name="状態",
            value="この募集は終了しました。",
            inline=False,
        )

        await interaction.response.edit_message(
            embed=embed,
            view=CustomRecruitmentView(disabled=True),
        )


# ============================================================
# カスタム募集の作成モーダル
# ============================================================

class CustomRecruitmentModal(discord.ui.Modal):

    def __init__(self):
        super().__init__(title="カスタム募集を作成")

        self.title_input = discord.ui.TextInput(
            label="募集タイトル",
            placeholder="例：5人でカスタムしよう！",
            max_length=100,
            required=True,
        )

        self.datetime_input = discord.ui.TextInput(
            label="開催日時",
            placeholder="例：2026/12/20 21:00",
            max_length=100,
            required=True,
        )

        self.details_input = discord.ui.TextInput(
            label="募集内容・詳細",
            placeholder="参加条件やルールなど",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False,
        )

        self.add_item(self.title_input)
        self.add_item(self.datetime_input)
        self.add_item(self.details_input)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        channel = await bot.fetch_channel(
            CUSTOM_PANEL_CHANNEL_ID
        )

        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(
                "カスタム募集チャンネルが見つかりません。",
                ephemeral=True,
            )
            return

        # 募集内容を作成
        embed = discord.Embed(
            title=f"🎮 {self.title_input.value.strip()}",
            description=(
                self.details_input.value.strip()
                if self.details_input.value.strip()
                else "参加者を募集しています！"
            ),
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="開催日時",
            value=self.datetime_input.value.strip(),
            inline=False,
        )

        embed.add_field(
            name="募集主",
            value=interaction.user.mention,
            inline=False,
        )

        set_custom_members(
            embed,
            "参加者",
            [],
        )

        set_custom_members(
            embed,
            "途中参加",
            [],
        )

        embed.set_footer(text=encode_hidden_user_id(interaction.user.id))

        try:
            await channel.send(
                content=(
                    f"<@&{CUSTOM_ROLE_ID}> "
                    "カスタム募集が立ち上がりました！"
                ),
                embed=embed,
                view=CustomRecruitmentView(),
                allowed_mentions=discord.AllowedMentions(
                    roles=True
                ),
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "カスタム募集チャンネルへの送信権限がありません。",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            await interaction.followup.send(
                "カスタム募集の作成に失敗しました。",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "カスタム募集を作成しました！",
            ephemeral=True,
        )


# ============================================================
# カスタム募集パネルのボタン
# ============================================================

class CustomRecruitmentPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="カスタムを募集する",
        style=discord.ButtonStyle.success,
        emoji="🎮",
        custom_id="nexus:custom:open",
    )
    async def open_custom_modal(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.send_modal(
            CustomRecruitmentModal()
        )


# ============================================================
# カスタム募集パネル設置コマンド
# ============================================================

@bot.tree.command(
    name="setup_custom_panel",
    description="カスタム募集パネルを設置します",
)
async def setup_custom_panel(
    interaction: discord.Interaction,
):

    if not is_owner(interaction.user):
        await interaction.response.send_message(
            "このコマンドは運営者専用です。",
            ephemeral=True,
        )
        return

    if interaction.guild is None:
        await interaction.response.send_message(
            "サーバー内で使用してください。",
            ephemeral=True,
        )
        return

    channel = interaction.guild.get_channel(
        CUSTOM_PANEL_CHANNEL_ID
    )

    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "カスタム募集チャンネルが見つかりません。",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="カスタム募集",
        description=(
            "カスタムを開催したい方は、下のボタンを押してください。\n\n"
            "開催日時・募集タイトル・詳細を入力すると、"
            "カスタム募集が投稿されます。\n\n"
            ""
        ),
        color=discord.Color.blurple(),
    )

    await channel.send(
        embed=embed,
        view=CustomRecruitmentPanelView(),
    )

    await interaction.response.send_message(
        "カスタム募集パネルを設置しました！",
        ephemeral=True,
    )


# ============================================================
# Part 7 終了
# ============================================================


# ============================================================
# Nexus BOT - Part 8 / 8
# ロール選択・BOT起動機能
# ============================================================


# ============================================================
# ロール選択ボタン
# ============================================================

class SelectableRoleButton(discord.ui.Button):

    def __init__(
        self,
        label: str,
        role_id: int,
        custom_id: str,
        emoji: str,
    ):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=custom_id,
            emoji=emoji,
        )

        self.role_id = role_id

    async def callback(
        self,
        interaction: discord.Interaction,
    ):
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "サーバー内で使用してください。",
                ephemeral=True,
            )
            return

        selected_role = guild.get_role(self.role_id)

        if selected_role is None:
            await interaction.response.send_message(
                "対象のロールが見つかりません。",
                ephemeral=True,
            )
            return

        # BOTのロール管理権限を確認
        if not guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "BOTにロール管理権限がありません。",
                ephemeral=True,
            )
            return

        try:
            # 選択したロールだけを追加し、他の選択済みロールは残す
            if selected_role not in interaction.user.roles:
                await interaction.user.add_roles(
                    selected_role,
                    reason="Nexus BOT ロール選択",
                )

        except discord.Forbidden:
            await interaction.response.send_message(
                "ロールを変更できませんでした。\n"
                "BOTのロールが対象ロールより上にあるか確認してください。",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            await interaction.response.send_message(
                "ロール変更中にエラーが発生しました。",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"**{selected_role.name}** を付与しました！",
            ephemeral=True,
        )


# ============================================================
# 全ロール解除ボタン
# ============================================================

class ClearSelectableRolesButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="全てのロールを外す",
            style=discord.ButtonStyle.danger,
            custom_id="nexus:roles:clear",
            emoji="🗑️",
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "サーバー内で使用してください。",
                ephemeral=True,
            )
            return

        if not guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "BOTにロール管理権限がありません。",
                ephemeral=True,
            )
            return

        remove_roles = [
            role
            for role in interaction.user.roles
            if role.id in SELECTABLE_ROLE_IDS
        ]

        if not remove_roles:
            await interaction.response.send_message(
                "外すロールはありません。",
                ephemeral=True,
            )
            return

        try:
            await interaction.user.remove_roles(
                *remove_roles,
                reason="Nexus BOT ロール全解除",
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "ロールを外せませんでした。\n"
                "BOTのロール位置を確認してください。",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            await interaction.response.send_message(
                "ロール解除中にエラーが発生しました。",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "選択対象のロールを全て外しました！",
            ephemeral=True,
        )


# ============================================================
# ロール選択パネル
# ============================================================

class RolePanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

        self.add_item(SelectableRoleButton(label="ノーマル", role_id=NORMAL_ROLE_ID, custom_id="nexus:roles:normal", emoji="🎮"))
        self.add_item(SelectableRoleButton(label="ランク", role_id=RANK_ROLE_ID, custom_id="nexus:roles:rank", emoji="💎"))
        self.add_item(SelectableRoleButton(label="カスタム", role_id=CUSTOM_ROLE_ID, custom_id="nexus:roles:custom", emoji="🛠️"))
        self.add_item(SelectableRoleButton(label="大会", role_id=TOURNAMENT_ROLE_ID, custom_id="nexus:roles:tournament", emoji="🏆"))
        self.add_item(ClearSelectableRolesButton())


# ============================================================
# ロール選択パネル設置コマンド
# ============================================================

@bot.tree.command(
    name="setup_role_panel",
    description="ロール選択パネルを設置します",
)
async def setup_role_panel(
    interaction: discord.Interaction,
):

    if not is_owner(interaction.user):
        await interaction.response.send_message(
            "このコマンドは運営者専用です。",
            ephemeral=True,
        )
        return

    if interaction.guild is None:
        await interaction.response.send_message(
            "サーバー内で使用してください。",
            ephemeral=True,
        )
        return

    channel = interaction.guild.get_channel(
        ROLE_PANEL_CHANNEL_ID
    )

    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "ロール選択チャンネルが見つかりません。",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="ロール選択",
        description=(
            "希望するロールを選択してください。\n\n"
            "🎮 **ノーマル**\n"
            "💎 **ランク**\n"
            "🛠️ **カスタム**\n"
            "🏆 **大会**\n\n"
            "必要なロールを何個でも選択できます。\n"
            "選択したロールは追加され、他のロールは外れません。\n\n"
            "🗑️ **全てのロールを外す**\n"
            "選択対象のロールを全て解除できます。"
        ),
        color=discord.Color.blurple(),
    )

    await channel.send(
        embed=embed,
        view=RolePanelView(),
    )

    await interaction.response.send_message(
        "ロール選択パネルを設置しました！",
        ephemeral=True,
    )


# ============================================================
# BOT再起動後の永続ボタン登録
# ============================================================

def register_persistent_views():

    # 選手登録パネル
    bot.add_view(
        RegistrationStartView()
    )

    # 大会募集
    bot.add_view(
        TournamentView()
    )

    # チーム申請パネル
    bot.add_view(
        TeamApplicationPanelView()
    )

    # 通常・ランク・Flex募集
    bot.add_view(
        RecruitmentView()
    )

    # カスタム募集パネル
    bot.add_view(
        CustomRecruitmentPanelView()
    )

    # カスタム募集
    bot.add_view(
        CustomRecruitmentView()
    )

    # ロール選択
    bot.add_view(
        RolePanelView()
    )

    logger.info("永続ボタンを登録しました。")


# ============================================================
# BOT起動
# ============================================================

if __name__ == "__main__":

    if not BOT_TOKEN:
        logger.critical(
            "DISCORD_TOKEN が設定されていません。"
        )

        raise RuntimeError(
            "Bot-Hostingの環境変数にDISCORD_TOKENを設定してください。"
        )

    register_persistent_views()

    logger.info("Nexus BOTを起動します。")

    bot.run(BOT_TOKEN)


# ============================================================
# Part 8 終了
# ============================================================
