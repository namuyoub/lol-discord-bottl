"""Player registration module."""
from bot_core import *

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
            max_values=len(MAIN_ROLE_CHOICES),
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

        # Modal送信の応答期限を確保し、以降はfollowupで結果を返す
        await interaction.response.defer(ephemeral=True)

        riot_id = normalize_riot_id(str(self.riot_id.value))

        if make_opgg_url(riot_id) is None:
            await interaction.followup.send(
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
                await interaction.followup.send("FA Cardチャンネルが見つかりません。", ephemeral=True)
                return
            # 遅延インポートにしてFA Card側との循環参照を防ぐ
            from cogs.fa_card import OPggLinkView
            try:
                await channel.send(embed=embed, view=OPggLinkView(opgg_url))
            except discord.Forbidden:
                await interaction.followup.send("FA Cardチャンネルへの送信権限がありません。", ephemeral=True)
                return
            except discord.HTTPException:
                await interaction.followup.send("FA Cardの発行に失敗しました。", ephemeral=True)
                return
            await interaction.followup.send("FA Cardを発行しました！", ephemeral=True)
            return

        # Discordのニックネームは最大32文字
        rank_nickname = {
            "Platinum": "P",
            "Emerald": "E",
            "Diamond": "D",
            "Master": "M",
            "Grandmaster": "GM",
            "Challenger": "C",
        }.get(self.rank, self.rank)
        nickname = (
            f"{game_name} / {roles_text} / {rank_nickname}"
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

        # 登録時にポジション・ランクロールを自動付与
        if guild.me and guild.me.guild_permissions.manage_roles:
            assign_role_ids = [
                POSITION_ROLE_IDS[role]
                for role in self.roles
                if role in POSITION_ROLE_IDS
            ]
            rank_role_id = RANK_ROLE_IDS.get(self.rank)
            if rank_role_id:
                assign_role_ids.append(rank_role_id)

            roles_to_add = [
                guild.get_role(role_id)
                for role_id in dict.fromkeys(assign_role_ids)
            ]
            roles_to_add = [
                role for role in roles_to_add
                if role is not None and role not in interaction.user.roles
            ]
            if roles_to_add:
                try:
                    await interaction.user.add_roles(
                        *roles_to_add,
                        reason="Nexus選手登録：ランク・ポジション自動付与",
                    )
                except discord.Forbidden:
                    logger.warning("選手登録ロール付与の権限不足: user=%s", interaction.user.id)
                except discord.HTTPException:
                    logger.exception("選手登録ロール付与に失敗: user=%s", interaction.user.id)
        else:
            logger.warning("選手登録ロール付与不可（manage_roles不足）")

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
            await interaction.followup.send(
                "登録情報は受け取りましたが、"
                "確認用チャンネルが見つかりません。\n"
                "運営者に連絡してください。",
                ephemeral=True,
            )
            return

        try:
            await check_channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send(
                "確認用チャンネルへの送信権限がありません。",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
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
