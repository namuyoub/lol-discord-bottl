"""FA Card module."""
from bot_core import *
from cogs.registration import RegistrationSelectView

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
