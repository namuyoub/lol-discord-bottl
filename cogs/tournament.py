"""Tournament recruitment module."""
from bot_core import *

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
