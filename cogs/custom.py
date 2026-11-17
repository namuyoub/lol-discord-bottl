"""Custom game recruitment module."""
from bot_core import *

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
        # 先に応答をACKして3秒タイムアウトを回避
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

        try:
            channel = await bot.fetch_channel(
                CUSTOM_PANEL_CHANNEL_ID
            )
        except discord.HTTPException:
            logger.exception(
                "カスタム募集チャンネルの取得に失敗しました: %s",
                CUSTOM_PANEL_CHANNEL_ID,
            )
            await interaction.followup.send(
                "カスタム募集チャンネルを取得できませんでした。運営者に連絡してください。",
                ephemeral=True,
            )
            return

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
