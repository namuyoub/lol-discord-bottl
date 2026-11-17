"""Selectable server roles module."""
from bot_core import *

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
