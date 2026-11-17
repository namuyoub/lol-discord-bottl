"""Private team channel module."""
from bot_core import *

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
