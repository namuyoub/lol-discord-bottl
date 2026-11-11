# ============================================================
# Nexus BOT
# Discord.py 2.x
# ============================================================

import discord
from discord.ext import commands
from discord import app_commands

import asyncio
import logging
import os
import re
from datetime import datetime
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
# 登録ランク
# ============================================================

RANK_CHOICES = [
    "Challenger",
    "Grandmaster",
    "Master",
    "Diamond I–II",
    "Diamond III–IV",
    "Emerald I–II",
    "Emerald III–IV",
    "Platinum I",
    "Platinum II",
    "Platinum III",
    "Platinum IV",
]

# ============================================================
# メインロール
# ============================================================

MAIN_ROLE_CHOICES = [
    "TOP",
    "JG",
    "MID",
    "ADC",
    "SUP",
]

# ============================================================
# Embedカラー
# ============================================================

RANK_COLORS = {
    "Challenger": 0xE74C3C,
    "Grandmaster": 0x9B59B6,
    "Master": 0x3498DB,
    "Diamond I–II": 0x00BFFF,
    "Diamond III–IV": 0x1ABC9C,
    "Emerald I–II": 0x2ECC71,
    "Emerald III–IV": 0x27AE60,
    "Platinum I": 0x48C9B0,
    "Platinum II": 0x45B39D,
    "Platinum III": 0x16A085,
    "Platinum IV": 0x117A65,
}

DEFAULT_COLOR = 0x5865F2
SUCCESS_COLOR = 0x2ECC71
ERROR_COLOR = 0xE74C3C
WARNING_COLOR = 0xF1C40F

# ============================================================
# 募集設定
# ============================================================

CUSTOM_RECRUIT_PER_LIST = 3

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
        timestamp=None,
    )


def create_rank_embed(
    title: str,
    description: str,
    rank: str,
) -> discord.Embed:
    return create_embed(
        title=title,
        description=description,
        color=RANK_COLORS.get(rank, DEFAULT_COLOR),
    )


def success_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return create_embed(
        f"✅ {title}",
        description,
        SUCCESS_COLOR,
    )


def error_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return create_embed(
        f"❌ {title}",
        description,
        ERROR_COLOR,
    )


def warning_embed(
    title: str,
    description: str,
) -> discord.Embed:
    return create_embed(
        f"⚠️ {title}",
        description,
        WARNING_COLOR,
    )


# ============================================================
# 共通権限チェック
# ============================================================

def is_owner(user: discord.abc.User) -> bool:
    return user.id == OWNER_ID


def can_manage_recruit(
    user: discord.abc.User,
    recruiter_id: int,
) -> bool:
    return (
        user.id == recruiter_id
        or user.id == OWNER_ID
    )


def can_manage_participant(
    user: discord.abc.User,
    participant_id: int,
) -> bool:
    return (
        user.id == participant_id
        or user.id == OWNER_ID
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
        logger.info("Nexus BOT 起動準備完了")

        guild = discord.Object(id=GUILD_ID)

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
# Riot ID 登録機能
# ============================================================

class RegistrationRankSelect(discord.ui.Select):

    def __init__(self):
        options = [
            discord.SelectOption(label=rank, value=rank)
            for rank in RANK_CHOICES
        ]

        super().__init__(
            placeholder="最高ランクを選択してください",
            options=options,
            min_values=1,
            max_values=1,
            custom_id="nexus_registration_rank",
        )

    async def callback(self, interaction: discord.Interaction):

        self.view.rank = self.values[0]

        await interaction.response.send_message(
            "メインロールを選択してください。",
            view=RegistrationRoleSelectView(self.view),
            ephemeral=True,
        )


class RegistrationRoleSelect(discord.ui.Select):

    def __init__(self, registration_view):

        self.registration_view = registration_view

        options = [
            discord.SelectOption(label=role, value=role)
            for role in MAIN_ROLE_CHOICES
        ]

        super().__init__(
            placeholder="メインロールを選択してください",
            options=options,
            min_values=1,
            max_values=5,
            custom_id="nexus_registration_roles",
        )

    async def callback(self, interaction: discord.Interaction):

        self.registration_view.roles = self.values

        await interaction.response.send_modal(
            RegistrationModal(self.registration_view)
        )


class RegistrationRoleSelectView(discord.ui.View):

    def __init__(self, registration_view):

        super().__init__(timeout=180)

        self.add_item(
            RegistrationRoleSelect(registration_view)
        )


class RegistrationModal(discord.ui.Modal):

    def __init__(self, registration_view):

        self.registration_view = registration_view

        super().__init__(
            title="Riot ID 登録",
            timeout=300,
            custom_id="nexus_registration_modal",
        )

        self.riot_id = discord.ui.TextInput(
            label="Riot ID（Name#Tag）",
            placeholder="Player#JP1",
            max_length=100,
            required=True,
        )

        self.self_pr = discord.ui.TextInput(
            label="自己PR",
            placeholder="自分の得意なことなど",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )

        self.add_item(self.riot_id)
        self.add_item(self.self_pr)

    async def on_submit(self, interaction: discord.Interaction):

        riot_id = str(self.riot_id.value).strip()
        self_pr = str(self.self_pr.value).strip()

        if "#" not in riot_id:

            await interaction.response.send_message(
                "Riot IDは `Name#Tag` の形式で入力してください。",
                ephemeral=True,
            )
            return

        name, tag = riot_id.split("#", 1)

        if not name or not tag:

            await interaction.response.send_message(
                "Riot IDの入力内容を確認してください。",
                ephemeral=True,
            )
            return

        rank = self.registration_view.rank
        roles = self.registration_view.roles

        member = interaction.user

        nickname = (
            f"{name} / {'・'.join(roles)} / {rank}"
        )

        nickname = nickname[:32]

        try:

            if isinstance(member, discord.Member):

                await member.edit(
                    nick=nickname,
                    reason="Nexus BOT Riot ID登録",
                )

        except discord.Forbidden:

            logger.warning(
                f"ニックネーム変更権限なし: {member.id}"
            )

        except discord.HTTPException:

            logger.exception(
                f"ニックネーム変更失敗: {member.id}"
            )

        channel = interaction.guild.get_channel(
            INPUT_CHECK_CHANNEL_ID
        )

        if channel is None:

            await interaction.response.send_message(
                "登録確認チャンネルが見つかりません。",
                ephemeral=True,
            )
            return

        embed = create_rank_embed(
            title="Riot ID 登録情報",
            description=(
                f"**Discordユーザー:** {member.mention}\n"
                f"**Riot ID:** {riot_id}\n"
                f"**最高ランク:** {rank}\n"
                f"**メインロール:** {'・'.join(roles)}\n\n"
                f"**自己PR:**\n{self_pr}"
            ),
            rank=rank,
        )

        await channel.send(embed=embed)

        await interaction.response.send_message(
            "登録情報を送信しました！",
            ephemeral=True,
        )


class RegistrationStartView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(
        label="登録する",
        style=discord.ButtonStyle.success,
        custom_id="nexus_registration_start",
    )
    async def registration_start(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        view = RegistrationRankSelectView()

        await interaction.response.send_message(
            "最高ランクを選択してください。",
            view=view,
            ephemeral=True,
        )


class RegistrationRankSelectView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=180)

        self.rank = None
        self.roles = []

        self.add_item(RegistrationRankSelect())


@bot.tree.command(
    name="setup_registration",
    description="Riot ID登録パネルを設置する",
)
async def setup_registration(
    interaction: discord.Interaction,
):

    if not is_owner(interaction.user):

        await interaction.response.send_message(
            "管理者のみ実行できます。",
            ephemeral=True,
        )
        return

    channel = interaction.guild.get_channel(
        REGISTRATION_CHANNEL_ID
    )

    if channel is None:

        await interaction.response.send_message(
            "登録チャンネルが見つかりません。",
            ephemeral=True,
        )
        return

    embed = create_embed(
        title="Riot ID 登録",
        description=(
            "Nexus Serverで使用するRiot IDを登録してください。\n\n"
            "下のボタンから登録を開始できます。"
        ),
    )

    await channel.send(
        embed=embed,
        view=RegistrationStartView(),
    )

    await interaction.response.send_message(
        "登録パネルを設置しました。",
        ephemeral=True,
    )
# ============================================================
# FA Card 機能
# ============================================================

class FACardRankSelect(discord.ui.Select):

    def __init__(self):

        options = [
            discord.SelectOption(label=rank, value=rank)
            for rank in RANK_CHOICES
        ]

        super().__init__(
            placeholder="最高ランクを選択してください",
            options=options,
            min_values=1,
            max_values=1,
            custom_id="nexus_fa_rank",
        )

    async def callback(self, interaction: discord.Interaction):

        self.view.rank = self.values[0]

        await interaction.response.send_message(
            "メインロールを選択してください。",
            view=FACardRoleSelectView(self.view),
            ephemeral=True,
        )


class FACardRoleSelect(discord.ui.Select):

    def __init__(self, fa_view):

        self.fa_view = fa_view

        options = [
            discord.SelectOption(label=role, value=role)
            for role in MAIN_ROLE_CHOICES
        ]

        super().__init__(
            placeholder="メインロールを選択してください",
            options=options,
            min_values=1,
            max_values=5,
            custom_id="nexus_fa_roles",
        )

    async def callback(self, interaction: discord.Interaction):

        self.fa_view.roles = self.values

        await interaction.response.send_modal(
            FACardModal(self.fa_view)
        )


class FACardRoleSelectView(discord.ui.View):

    def __init__(self, fa_view):

        super().__init__(timeout=180)

        self.add_item(
            FACardRoleSelect(fa_view)
        )


class FACardModal(discord.ui.Modal):

    def __init__(self, fa_view):

        self.fa_view = fa_view

        super().__init__(
            title="FA Card 登録",
            timeout=300,
            custom_id="nexus_fa_modal",
        )

        self.riot_id = discord.ui.TextInput(
            label="Riot ID（Name#Tag）",
            placeholder="Player#JP1",
            max_length=100,
            required=True,
        )

        self.self_pr = discord.ui.TextInput(
            label="自己PR",
            placeholder="得意なこと・活動内容など",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )

        self.add_item(self.riot_id)
        self.add_item(self.self_pr)

    async def on_submit(self, interaction: discord.Interaction):

        riot_id = str(self.riot_id.value).strip()
        self_pr = str(self.self_pr.value).strip()

        if "#" not in riot_id:

            await interaction.response.send_message(
                "Riot IDは `Name#Tag` の形式で入力してください。",
                ephemeral=True,
            )
            return

        name, tag = riot_id.split("#", 1)

        if not name or not tag:

            await interaction.response.send_message(
                "Riot IDの入力内容を確認してください。",
                ephemeral=True,
            )
            return

        rank = self.fa_view.rank
        roles = self.fa_view.roles

        channel = interaction.guild.get_channel(
            FA_CARD_CHANNEL_ID
        )

        if channel is None:

            await interaction.response.send_message(
                "FA Cardチャンネルが見つかりません。",
                ephemeral=True,
            )
            return

        embed = create_rank_embed(
            title=f"FA PLAYER：{name}",
            description=(
                f"**Riot ID:** {riot_id}\n"
                f"**最高ランク:** {rank}\n"
                f"**メインロール:** {'・'.join(roles)}\n\n"
                f"**自己PR:**\n{self_pr}"
            ),
            rank=rank,
        )

        # 投稿者のDiscord情報は公開Embedに表示しない
        await channel.send(embed=embed)

        await interaction.response.send_message(
            "FA Cardを投稿しました！",
            ephemeral=True,
        )


class FACardRankSelectView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=180)

        self.rank = None
        self.roles = []

        self.add_item(FACardRankSelect())


@bot.tree.command(
    name="fa_card",
    description="FA Cardを投稿する",
)
async def fa_card(
    interaction: discord.Interaction,
):

    if not is_owner(interaction.user):

        await interaction.response.send_message(
            "管理者のみ実行できます。",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        "最高ランクを選択してください。",
        view=FACardRankSelectView(),
        ephemeral=True,
    )
# ============================================================
# 大会募集機能
# ============================================================

class TournamentJoinModal(discord.ui.Modal):

    def __init__(self, tournament_view):

        self.tournament_view = tournament_view

        super().__init__(
            title="大会参加登録",
            timeout=300,
        )

        self.team_name = discord.ui.TextInput(
            label="チーム名",
            placeholder="参加するチーム名",
            max_length=100,
            required=True,
        )

        self.add_item(self.team_name)

    async def on_submit(self, interaction: discord.Interaction):

        team_name = str(self.team_name.value).strip()

        if not team_name:

            await interaction.response.send_message(
                "チーム名を入力してください。",
                ephemeral=True,
            )
            return

        message = self.tournament_view.message

        embed = message.embeds[0]

        participants = self.tournament_view.participants

        participants[interaction.user.id] = {
            "team": team_name,
            "status": "参加",
        }

        self.tournament_view.update_embed(embed)

        await message.edit(
            embed=embed,
            view=self.tournament_view,
        )

        await interaction.response.send_message(
            f"大会に参加登録しました！\nチーム名：{team_name}",
            ephemeral=True,
        )


class TournamentDeclineModal(discord.ui.Modal):

    def __init__(self, tournament_view):

        self.tournament_view = tournament_view

        super().__init__(
            title="大会参加辞退",
            timeout=300,
        )

        self.team_name = discord.ui.TextInput(
            label="辞退するチーム名",
            placeholder="登録したチーム名を入力",
            max_length=100,
            required=True,
        )

        self.add_item(self.team_name)

    async def on_submit(self, interaction: discord.Interaction):

        team_name = str(self.team_name.value).strip()

        participant = self.tournament_view.participants.get(
            interaction.user.id
        )

        if participant is None:

            await interaction.response.send_message(
                "参加登録が見つかりません。",
                ephemeral=True,
            )
            return

        if participant["team"] != team_name:

            await interaction.response.send_message(
                "登録したチーム名と一致しません。",
                ephemeral=True,
            )
            return

        del self.tournament_view.participants[
            interaction.user.id
        ]

        embed = self.tournament_view.message.embeds[0]

        self.tournament_view.update_embed(embed)

        await self.tournament_view.message.edit(
            embed=embed,
            view=self.tournament_view,
        )

        await interaction.response.send_message(
            "大会参加を辞退しました。",
            ephemeral=True,
        )


class TournamentView(discord.ui.View):

    def __init__(
        self,
        recruiter_id,
        tournament_name,
        event_date,
        deadline,
        details,
    ):

        super().__init__(timeout=None)

        self.recruiter_id = recruiter_id
        self.tournament_name = tournament_name
        self.event_date = event_date
        self.deadline = deadline
        self.details = details

        self.participants = {}
        self.message = None
        self.closed = False

    def update_embed(self, embed):

        participant_text = []

        for user_id, data in self.participants.items():

            participant_text.append(
                f"<@{user_id}>：{data['team']}"
            )

        if not participant_text:
            participant_text = ["参加者なし"]

        embed.clear_fields()

        embed.add_field(
            name="参加チーム",
            value="\n".join(participant_text),
            inline=False,
        )

        if self.closed:

            embed.add_field(
                name="募集状況",
                value="募集終了",
                inline=False,
            )

    @discord.ui.button(
        label="参加する",
        style=discord.ButtonStyle.success,
        custom_id="nexus_tournament_join",
    )
    async def join(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        if self.closed:

            await interaction.response.send_message(
                "この大会募集は終了しています。",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            TournamentJoinModal(self)
        )

    @discord.ui.button(
        label="辞退する",
        style=discord.ButtonStyle.danger,
        custom_id="nexus_tournament_decline",
    )
    async def decline(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        if self.closed:

            await interaction.response.send_message(
                "この大会募集は終了しています。",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            TournamentDeclineModal(self)
        )

    @discord.ui.button(
        label="募集を終了する",
        style=discord.ButtonStyle.secondary,
        custom_id="nexus_tournament_close",
    )
    async def close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        if not can_manage_recruit(
            interaction.user,
            self.recruiter_id,
        ):

            await interaction.response.send_message(
                "募集作成者またはBOT管理者のみ終了できます。",
                ephemeral=True,
            )
            return

        self.closed = True

        for item in self.children:

            if item.label != "募集を終了する":
                item.disabled = True

        embed = self.message.embeds[0]

        self.update_embed(embed)

        await self.message.edit(
            embed=embed,
            view=self,
        )

        await interaction.response.send_message(
            "大会募集を終了しました。",
            ephemeral=True,
        )


class TournamentCreateModal(discord.ui.Modal):

    def __init__(self):

        super().__init__(
            title="大会募集作成",
            timeout=300,
        )

        self.tournament_name = discord.ui.TextInput(
            label="大会名",
            placeholder="大会名を入力",
            max_length=100,
            required=True,
        )

        self.event_date = discord.ui.TextInput(
            label="開催日時",
            placeholder="2026-12-01 20:00",
            max_length=30,
            required=True,
        )

        self.deadline = discord.ui.TextInput(
            label="締切日時",
            placeholder="2026-11-30 23:59",
            max_length=30,
            required=True,
        )

        self.details = discord.ui.TextInput(
            label="大会詳細",
            placeholder="ルール・参加条件など",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True,
        )

        self.add_item(self.tournament_name)
        self.add_item(self.event_date)
        self.add_item(self.deadline)
        self.add_item(self.details)

    async def on_submit(self, interaction: discord.Interaction):

        channel = interaction.guild.get_channel(
            TOURNAMENT_CHANNEL_ID
        )

        if channel is None:

            await interaction.response.send_message(
                "大会募集チャンネルが見つかりません。",
                ephemeral=True,
            )
            return

        tournament_name = str(
            self.tournament_name.value
        ).strip()

        event_date = str(
            self.event_date.value
        ).strip()

        deadline = str(
            self.deadline.value
        ).strip()

        details = str(
            self.details.value
        ).strip()

        embed = create_embed(
            title=tournament_name,
            description=(
                f"**開催日**\n{event_date}\n\n"
                f"**締切日**\n{deadline}\n\n"
                f"**大会詳細**\n{details}"
            ),
        )

        view = TournamentView(
            recruiter_id=interaction.user.id,
            tournament_name=tournament_name,
            event_date=event_date,
            deadline=deadline,
            details=details,
        )

        message = await channel.send(
            embed=embed,
            view=view,
        )

        view.message = message

        await interaction.response.send_message(
            "大会募集を作成しました！",
            ephemeral=True,
        )


@bot.tree.command(
    name="tournament_create",
    description="大会募集を作成する",
)
async def tournament_create(
    interaction: discord.Interaction,
):

    if not is_owner(interaction.user):

        await interaction.response.send_message(
            "管理者のみ実行できます。",
            ephemeral=True,
        )
        return

    await interaction.response.send_modal(
        TournamentCreateModal()
    )
# ============================================================
# チーム結成・解散申請機能
# ============================================================

class TeamApplicationView(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

    @discord.ui.button(
        label="チーム結成",
        style=discord.ButtonStyle.success,
        custom_id="nexus_team_create",
    )
    async def team_create(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await create_team_application_channel(
            interaction,
            "チーム結成",
        )

    @discord.ui.button(
        label="チーム解散",
        style=discord.ButtonStyle.danger,
        custom_id="nexus_team_disband",
    )
    async def team_disband(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await create_team_application_channel(
            interaction,
            "チーム解散",
        )


async def create_team_application_channel(
    interaction: discord.Interaction,
    channel_name: str,
):

    guild = interaction.guild

    category = guild.get_channel(
        TEAM_APPLICATION_CATEGORY_ID
    )

    if category is None:

        await interaction.response.send_message(
            "申請カテゴリが見つかりません。",
            ephemeral=True,
        )
        return

    # ========================================================
    # チャンネル作成
    # ========================================================

    safe_name = re.sub(
        r"[^a-zA-Z0-9ぁ-んァ-ン一-龯ー]",
        "-",
        interaction.user.display_name,
    )

    safe_name = safe_name.lower()[:30]

    channel_name_with_user = (
        f"{channel_name}-{safe_name}"
    )

    overwrites = {

        guild.default_role: discord.PermissionOverwrite(
            view_channel=False,
        ),

        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
        ),

        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
        ),
    }

    owner = guild.get_member(OWNER_ID)

    if owner:

        overwrites[owner] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
        )

    channel = await guild.create_text_channel(
        name=channel_name_with_user,
        category=category,
        overwrites=overwrites,
        reason="Nexus BOT チーム申請",
    )

    embed = create_embed(
        title=f"{channel_name}申請",
        description=(
            f"{interaction.user.mention} さんの申請チャンネルです。\n\n"
            "こちらで管理者と相談してください。"
        ),
    )

    await channel.send(
        content=interaction.user.mention,
        embed=embed,
    )

    await interaction.response.send_message(
        f"申請チャンネルを作成しました。\n{channel.mention}",
        ephemeral=True,
    )


@bot.tree.command(
    name="setup_team_application",
    description="チーム申請パネルを設置する",
)
async def setup_team_application(
    interaction: discord.Interaction,
):

    if not is_owner(interaction.user):

        await interaction.response.send_message(
            "管理者のみ実行できます。",
            ephemeral=True,
        )
        return

    channel = interaction.guild.get_channel(
        TEAM_APPLICATION_CATEGORY_ID
    )

    if channel is None:

        await interaction.response.send_message(
            "申請カテゴリが見つかりません。",
            ephemeral=True,
        )
        return

    embed = create_embed(
        title="チーム申請",
        description=(
            "チームの結成・解散申請はこちらから行ってください。\n\n"
            "チーム結成：新しくチームを作る場合\n"
            "チーム解散：チームを解散する場合"
        ),
    )

    await channel.send(
        embed=embed,
        view=TeamApplicationView(),
    )

    await interaction.response.send_message(
        "チーム申請パネルを設置しました。",
        ephemeral=True,
    )
# ============================================================
# ノーマル募集機能
# ============================================================

class NormalRecruitView(discord.ui.View):

    def __init__(self, recruiter_id: int):
        super().__init__(timeout=None)

        self.recruiter_id = recruiter_id
        self.closed = False

    async def update_status(
        self,
        interaction: discord.Interaction,
        status: str,
    ):

        if self.closed:
            await interaction.response.send_message(
                "この募集は終了しています。",
                ephemeral=True,
            )
            return

        embed = create_embed(
            title="ノーマル募集",
            description=(
                f"{interaction.user.mention} さんが"
                f"{status}\n"
            ),
        )

        await interaction.channel.send(embed=embed)

        await interaction.response.send_message(
            "操作しました！",
            ephemeral=True,
        )

    @discord.ui.button(
        label="参加する",
        style=discord.ButtonStyle.success,
        custom_id="nexus_normal_join",
    )
    async def join(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.update_status(
            interaction,
            "参加してくれるよ！",
        )

    @discord.ui.button(
        label="途中参加する",
        style=discord.ButtonStyle.primary,
        custom_id="nexus_normal_late",
    )
    async def late(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.update_status(
            interaction,
            "途中で参加くるよ〜",
        )

    @discord.ui.button(
        label="辞退する",
        style=discord.ButtonStyle.danger,
        custom_id="nexus_normal_decline",
    )
    async def decline(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.update_status(
            interaction,
            "辞退したからね〜",
        )

    @discord.ui.button(
        label="募集を終了する",
        style=discord.ButtonStyle.secondary,
        custom_id="nexus_normal_close",
    )
    async def close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        if not can_manage_recruit(
            interaction.user,
            self.recruiter_id,
        ):
            await interaction.response.send_message(
                "募集作成者またはBOT管理者のみ終了できます。",
                ephemeral=True,
            )
            return

        self.closed = True

        for item in self.children:
            item.disabled = True

        await interaction.message.edit(
            view=self,
        )

        await interaction.channel.send(
            "🔒 **この募集は終了しました。**"
        )

        await interaction.response.send_message(
            "募集を終了しました。",
            ephemeral=True,
        )


# ============================================================
# ノーマル募集チャンネル投稿処理
# ============================================================

@bot.event
async def on_message(message: discord.Message):

    if message.author.bot:
        return

    # ========================================================
    # ノーマル募集
    # ========================================================

    if message.channel.id == NORMAL_RECRUIT_CHANNEL_ID:

        try:

            thread = await message.create_thread(
                name=f"ノーマル募集-{message.author.display_name}",
                auto_archive_duration=1440,
            )

            embed = create_embed(
                title="ノーマル募集",
                description=(
                    f"{message.author.mention} さんが立ち上げました！\n\n"
                    f"**募集内容**\n{message.content or '募集内容なし'}"
                ),
            )

            await thread.send(
                content=f"{message.author.mention} <@&{NORMAL_ROLE_ID}>",
                embed=embed,
                view=NormalRecruitView(message.author.id),
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                    roles=True,
                    everyone=False,
                ),
            )

        except discord.Forbidden:
            logger.warning(
                "ノーマル募集チャンネルのスレッド作成権限がありません。"
            )

        except discord.HTTPException:
            logger.exception(
                "ノーマル募集スレッド作成失敗"
            )

    await bot.process_commands(message)
# ============================================================
# ランク募集機能
# ============================================================

class RankRecruitView(discord.ui.View):

    def __init__(self, recruiter_id: int):
        super().__init__(timeout=None)

        self.recruiter_id = recruiter_id
        self.closed = False

    async def update_status(
        self,
        interaction: discord.Interaction,
        status: str,
    ):

        if self.closed:
            await interaction.response.send_message(
                "この募集は終了しています。",
                ephemeral=True,
            )
            return

        embed = create_embed(
            title="ランク募集",
            description=(
                f"{interaction.user.mention} さんが"
                f"{status}\n"
            ),
        )

        await interaction.channel.send(embed=embed)

        await interaction.response.send_message(
            "操作しました！",
            ephemeral=True,
        )

    @discord.ui.button(
        label="参加する",
        style=discord.ButtonStyle.success,
        custom_id="nexus_rank_join",
    )
    async def join(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.update_status(
            interaction,
            "参加してくれるよ！",
        )

    @discord.ui.button(
        label="途中参加する",
        style=discord.ButtonStyle.primary,
        custom_id="nexus_rank_late",
    )
    async def late(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.update_status(
            interaction,
            "途中で参加くるよ〜",
        )

    @discord.ui.button(
        label="辞退する",
        style=discord.ButtonStyle.danger,
        custom_id="nexus_rank_decline",
    )
    async def decline(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.update_status(
            interaction,
            "辞退したからね〜",
        )

    @discord.ui.button(
        label="募集を終了する",
        style=discord.ButtonStyle.secondary,
        custom_id="nexus_rank_close",
    )
    async def close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        if not can_manage_recruit(
            interaction.user,
            self.recruiter_id,
        ):
            await interaction.response.send_message(
                "募集作成者またはBOT管理者のみ終了できます。",
                ephemeral=True,
            )
            return

        self.closed = True

        for item in self.children:
            item.disabled = True

        await interaction.message.edit(
            view=self,
        )

        await interaction.channel.send(
            "🔒 **この募集は終了しました。**"
        )

        await interaction.response.send_message(
            "募集を終了しました。",
            ephemeral=True,
        )


# ============================================================
# ランク募集チャンネル投稿処理
# ============================================================

@bot.event
async def rank_recruit_message(message: discord.Message):

    if message.author.bot:
        return

    if message.channel.id != RANK_RECRUIT_CHANNEL_ID:
        return

    try:

        thread = await message.create_thread(
            name=f"ランク募集-{message.author.display_name}",
            auto_archive_duration=1440,
        )

        embed = create_embed(
            title="ランク募集",
            description=(
                f"{message.author.mention} さんが立ち上げました！\n\n"
                f"**募集内容**\n{message.content or '募集内容なし'}"
            ),
        )

        await thread.send(
            content=f"{message.author.mention} <@&{RANK_ROLE_ID}>",
            embed=embed,
            view=RankRecruitView(message.author.id),
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=True,
                everyone=False,
            ),
        )

    except discord.Forbidden:
        logger.warning(
            "ランク募集チャンネルのスレッド作成権限がありません。"
        )

    except discord.HTTPException:
        logger.exception(
            "ランク募集スレッド作成失敗"
        )


# ============================================================
# ランク募集イベント登録
# ============================================================

bot.add_listener(
    rank_recruit_message,
    "on_message",
)
# ============================================================
# Flex募集機能
# ============================================================

class FlexRecruitView(discord.ui.View):

    def __init__(self, recruiter_id: int):
        super().__init__(timeout=None)

        self.recruiter_id = recruiter_id
        self.closed = False

    async def update_status(
        self,
        interaction: discord.Interaction,
        status: str,
    ):

        if self.closed:
            await interaction.response.send_message(
                "この募集は終了しています。",
                ephemeral=True,
            )
            return

        embed = create_embed(
            title="Flex募集",
            description=(
                f"{interaction.user.mention} さんが"
                f"{status}\n"
            ),
        )

        await interaction.channel.send(embed=embed)

        await interaction.response.send_message(
            "操作しました！",
            ephemeral=True,
        )

    @discord.ui.button(
        label="参加する",
        style=discord.ButtonStyle.success,
        custom_id="nexus_flex_join",
    )
    async def join(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.update_status(
            interaction,
            "参加してくれるよ！",
        )

    @discord.ui.button(
        label="途中参加する",
        style=discord.ButtonStyle.primary,
        custom_id="nexus_flex_late",
    )
    async def late(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.update_status(
            interaction,
            "途中で参加くるよ〜",
        )

    @discord.ui.button(
        label="辞退する",
        style=discord.ButtonStyle.danger,
        custom_id="nexus_flex_decline",
    )
    async def decline(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.update_status(
            interaction,
            "辞退したからね〜",
        )

    @discord.ui.button(
        label="募集を終了する",
        style=discord.ButtonStyle.secondary,
        custom_id="nexus_flex_close",
    )
    async def close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        if not can_manage_recruit(
            interaction.user,
            self.recruiter_id,
        ):
            await interaction.response.send_message(
                "募集作成者またはBOT管理者のみ終了できます。",
                ephemeral=True,
            )
            return

        self.closed = True

        for item in self.children:
            item.disabled = True

        await interaction.message.edit(
            view=self,
        )

        await interaction.channel.send(
            "🔒 **この募集は終了しました。**"
        )

        await interaction.response.send_message(
            "募集を終了しました。",
            ephemeral=True,
        )


# ============================================================
# Flex募集チャンネル投稿処理
# ============================================================

async def flex_recruit_message(message: discord.Message):

    if message.author.bot:
        return

    if message.channel.id != FLEX_RECRUIT_CHANNEL_ID:
        return

    try:

        thread = await message.create_thread(
            name=f"Flex募集-{message.author.display_name}",
            auto_archive_duration=1440,
        )

        embed = create_embed(
            title="Flex募集",
            description=(
                f"{message.author.mention} さんが立ち上げました！\n\n"
                f"**募集内容**\n{message.content or '募集内容なし'}"
            ),
        )

        await thread.send(
            content=f"{message.author.mention} <@&{RANK_ROLE_ID}>",
            embed=embed,
            view=FlexRecruitView(message.author.id),
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=True,
                everyone=False,
            ),
        )

    except discord.Forbidden:
        logger.warning(
            "Flex募集チャンネルのスレッド作成権限がありません。"
        )

    except discord.HTTPException:
        logger.exception(
            "Flex募集スレッド作成失敗"
        )


# ============================================================
# Flex募集イベント登録
# ============================================================

bot.add_listener(
    flex_recruit_message,
    "on_message",
)
# ============================================================
# カスタム募集機能
# ============================================================

custom_recruit_count = 0


class CustomRecruitModal(discord.ui.Modal):

    def __init__(self):
        super().__init__(
            title="カスタム募集作成",
            timeout=300,
        )

        self.date = discord.ui.TextInput(
            label="開催日",
            placeholder="2026-11-20",
            max_length=30,
            required=True,
        )

        self.time = discord.ui.TextInput(
            label="開催時間",
            placeholder="21:00",
            max_length=30,
            required=True,
        )

        self.title_input = discord.ui.TextInput(
            label="募集タイトル",
            placeholder="カスタム募集",
            max_length=100,
            required=True,
        )

        self.add_item(self.date)
        self.add_item(self.time)
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction):

        global custom_recruit_count

        channel = interaction.guild.get_channel(
            CUSTOM_PANEL_CHANNEL_ID
        )

        if channel is None:
            await interaction.response.send_message(
                "カスタム募集チャンネルが見つかりません。",
                ephemeral=True,
            )
            return

        custom_recruit_count += 1

        # 3件ごとに新しい募集投稿を作成
        if custom_recruit_count > CUSTOM_RECRUIT_PER_LIST:
            custom_recruit_count = 1

        date = str(self.date.value).strip()
        time = str(self.time.value).strip()
        title = str(self.title_input.value).strip()

        view = CustomRecruitView(
            recruiter_id=interaction.user.id,
            title=title,
            date=date,
            time=time,
        )

        embed = view.create_embed()

        message = await channel.send(
            content=f"<@&{CUSTOM_ROLE_ID}>",
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions(
                roles=True,
                users=False,
                everyone=False,
            ),
        )

        view.message = message

        await interaction.response.send_message(
            "カスタム募集を作成しました！",
            ephemeral=True,
        )


class CustomRecruitView(discord.ui.View):

    def __init__(
        self,
        recruiter_id: int,
        title: str,
        date: str,
        time: str,
    ):

        super().__init__(timeout=None)

        self.recruiter_id = recruiter_id
        self.title = title
        self.date = date
        self.time = time

        self.participants = []
        self.late_participants = []

        self.closed = False
        self.message = None

    def create_embed(self):

        embed = create_embed(
            title=self.title,
            description=(
                f"**開催日:** {self.date}\n"
                f"**開催時間:** {self.time}\n\n"
                f"**募集主:** <@{self.recruiter_id}>"
            ),
        )

        participants = (
            "\n".join(
                f"<@{user_id}>"
                for user_id in self.participants
            )
            or "参加者なし"
        )

        late_participants = (
            "\n".join(
                f"<@{user_id}>"
                for user_id in self.late_participants
            )
            or "途中参加者なし"
        )

        embed.add_field(
            name="参加者一覧",
            value=participants,
            inline=False,
        )

        embed.add_field(
            name="途中参加者一覧",
            value=late_participants,
            inline=False,
        )

        if self.closed:
            embed.add_field(
                name="募集状況",
                value="🔒 募集終了",
                inline=False,
            )

        return embed

    async def refresh(self):

        if self.message is None:
            return

        await self.message.edit(
            embed=self.create_embed(),
            view=self,
        )

    @discord.ui.button(
        label="参加する",
        style=discord.ButtonStyle.success,
        custom_id="nexus_custom_join",
    )
    async def join(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        if self.closed:
            await interaction.response.send_message(
                "募集は終了しています。",
                ephemeral=True,
            )
            return

        user_id = interaction.user.id

        if user_id not in self.participants:
            self.participants.append(user_id)

        if user_id in self.late_participants:
            self.late_participants.remove(user_id)

        await self.refresh()

        await interaction.response.send_message(
            "参加登録しました！",
            ephemeral=True,
        )

    @discord.ui.button(
        label="途中参加する",
        style=discord.ButtonStyle.primary,
        custom_id="nexus_custom_late",
    )
    async def late(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        if self.closed:
            await interaction.response.send_message(
                "募集は終了しています。",
                ephemeral=True,
            )
            return

        user_id = interaction.user.id

        if user_id not in self.late_participants:
            self.late_participants.append(user_id)

        if user_id in self.participants:
            self.participants.remove(user_id)

        await self.refresh()

        await interaction.response.send_message(
            "途中参加登録しました！",
            ephemeral=True,
        )

    @discord.ui.button(
        label="辞退する",
        style=discord.ButtonStyle.danger,
        custom_id="nexus_custom_decline",
    )
    async def decline(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        user_id = interaction.user.id

        if user_id in self.participants:
            self.participants.remove(user_id)

        if user_id in self.late_participants:
            self.late_participants.remove(user_id)

        await self.refresh()

        await interaction.response.send_message(
            "参加を辞退しました。",
            ephemeral=True,
        )

    @discord.ui.button(
        label="募集を終了する",
        style=discord.ButtonStyle.secondary,
        custom_id="nexus_custom_close",
    )
    async def close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        if not can_manage_recruit(
            interaction.user,
            self.recruiter_id,
        ):
            await interaction.response.send_message(
                "募集作成者またはBOT管理者のみ終了できます。",
                ephemeral=True,
            )
            return

        self.closed = True

        for item in self.children:
            item.disabled = True

        await self.refresh()

        await interaction.response.send_message(
            "募集を終了しました。",
            ephemeral=True,
        )


class CustomRecruitPanelView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="カスタムを募集する",
        style=discord.ButtonStyle.success,
        custom_id="nexus_custom_create",
    )
    async def create_custom(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await interaction.response.send_modal(
            CustomRecruitModal()
        )


@bot.tree.command(
    name="setup_custom",
    description="カスタム募集パネルを設置する",
)
async def setup_custom(
    interaction: discord.Interaction,
):

    if not is_owner(interaction.user):
        await interaction.response.send_message(
            "管理者のみ実行できます。",
            ephemeral=True,
        )
        return

    channel = interaction.guild.get_channel(
        CUSTOM_PANEL_CHANNEL_ID
    )

    if channel is None:
        await interaction.response.send_message(
            "カスタム募集チャンネルが見つかりません。",
            ephemeral=True,
        )
        return

    embed = create_embed(
        title="カスタム募集",
        description=(
            "カスタムゲームの募集はこちらから！\n\n"
            "下のボタンから募集を作成できます。"
        ),
    )

    await channel.send(
        embed=embed,
        view=CustomRecruitPanelView(),
    )

    await interaction.response.send_message(
        "カスタム募集パネルを設置しました。",
        ephemeral=True,
    )
# ============================================================
# ロール選択パネル
# ============================================================

class RoleSelectView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    async def change_role(
        self,
        interaction: discord.Interaction,
        role_id: int,
    ):

        role = interaction.guild.get_role(role_id)

        if role is None:
            await interaction.response.send_message(
                "ロールが見つかりません。",
                ephemeral=True,
            )
            return

        member = interaction.user

        if role in member.roles:
            await interaction.response.send_message(
                f"すでに {role.name} を持っています。",
                ephemeral=True,
            )
            return

        await member.add_roles(
            role,
            reason="ロール選択パネル",
        )

        await interaction.response.send_message(
            f"「{role.name}」を付与しました！",
            ephemeral=True,
        )

    async def remove_roles(
        self,
        interaction: discord.Interaction,
    ):

        role_ids = [
            NORMAL_ROLE_ID,
            RANK_ROLE_ID,
            CUSTOM_ROLE_ID,
            TOURNAMENT_ROLE_ID,
        ]

        roles = [
            interaction.guild.get_role(role_id)
            for role_id in role_ids
        ]

        roles = [
            role for role in roles
            if role is not None
            and role in interaction.user.roles
        ]

        if roles:
            await interaction.user.remove_roles(
                *roles,
                reason="ロール選択パネルで全解除",
            )

        await interaction.response.send_message(
            "対象のロールをすべて解除しました！",
            ephemeral=True,
        )

    @discord.ui.button(
        label="ノーマル",
        style=discord.ButtonStyle.primary,
        custom_id="nexus_role_normal",
    )
    async def normal(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.change_role(
            interaction,
            NORMAL_ROLE_ID,
        )

    @discord.ui.button(
        label="ランク",
        style=discord.ButtonStyle.primary,
        custom_id="nexus_role_rank",
    )
    async def rank(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.change_role(
            interaction,
            RANK_ROLE_ID,
        )

    @discord.ui.button(
        label="カスタム",
        style=discord.ButtonStyle.primary,
        custom_id="nexus_role_custom",
    )
    async def custom(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.change_role(
            interaction,
            CUSTOM_ROLE_ID,
        )

    @discord.ui.button(
        label="大会",
        style=discord.ButtonStyle.primary,
        custom_id="nexus_role_tournament",
    )
    async def tournament(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.change_role(
            interaction,
            TOURNAMENT_ROLE_ID,
        )

    @discord.ui.button(
        label="全ロール解除",
        style=discord.ButtonStyle.danger,
        custom_id="nexus_role_remove_all",
    )
    async def remove_all(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        await self.remove_roles(interaction)


@bot.tree.command(
    name="setup_roles",
    description="ロール選択パネルを設置する",
)
async def setup_roles(
    interaction: discord.Interaction,
):

    if not is_owner(interaction.user):
        await interaction.response.send_message(
            "管理者のみ実行できます。",
            ephemeral=True,
        )
        return

    channel = interaction.guild.get_channel(
        ROLE_PANEL_CHANNEL_ID
    )

    if channel is None:
        await interaction.response.send_message(
            "ロール選択チャンネルが見つかりません。",
            ephemeral=True,
        )
        return

    embed = create_embed(
        title="ロール選択",
        description=(
            "あなたが希望するロールを選択してください！\n\n"
            "🔵 ノーマル\n"
            "🔵 ランク\n"
            "🔵 カスタム\n"
            "🔵 大会\n\n"
            "右端の「全ロール解除」で対象ロールを外せます。"
        ),
    )

    await channel.send(
        embed=embed,
        view=RoleSelectView(),
    )

    await interaction.response.send_message(
        "ロール選択パネルを設置しました。",
        ephemeral=True,
    )
# ============================================================
# BOT起動・永続ボタン登録
# ============================================================

@bot.event
async def on_error(event, *args, **kwargs):
    logger.exception(
        f"イベントエラー: {event}"
    )


@bot.event
async def on_command_error(
    ctx,
    error,
):

    if isinstance(error, commands.CommandNotFound):
        return

    logger.exception(
        "コマンドエラー",
        exc_info=error,
    )


@bot.event
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):

    logger.exception(
        "スラッシュコマンドエラー",
        exc_info=error,
    )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                "エラーが発生しました。",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "エラーが発生しました。",
                ephemeral=True,
            )
    except discord.HTTPException:
        pass


# ============================================================
# 再起動後の永続ボタン登録
# ============================================================

@bot.event
async def setup_hook():

    # ロール選択
    bot.add_view(RoleSelectView())

    # カスタム募集パネル
    bot.add_view(CustomRecruitPanelView())

    # 通常募集
    bot.add_view(NormalRecruitView(OWNER_ID))

    # ランク募集
    bot.add_view(RankRecruitView(OWNER_ID))

    # Flex募集
    bot.add_view(FlexRecruitView(OWNER_ID))

    # サーバー限定スラッシュコマンド同期
    guild = discord.Object(
        id=GUILD_ID
    )

    bot.tree.copy_global_to(
        guild=guild
    )

    await bot.tree.sync(
        guild=guild
    )

    logger.info(
        "永続ボタン登録・コマンド同期完了"
    )


# ============================================================
# BOT起動
# ============================================================

if not BOT_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN が設定されていません。"
    )

bot.run(
    BOT_TOKEN
)
