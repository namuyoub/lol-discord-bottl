"""Normal, ranked and flex recruitment module."""
from bot_core import *

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
        await interaction.followup.send("参加状況を更新しました。", ephemeral=True)

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
