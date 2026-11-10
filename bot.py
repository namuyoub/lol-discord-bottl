# Nexus League Bot - runnable starter/completion
# Python 3.10+ / discord.py 2.x
# Token is read from the DISCORD_TOKEN environment variable.

import os
import sqlite3
import threading
from urllib.parse import quote

import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask

# ---------- Configuration ----------
TOKEN = os.getenv("DISCORD_TOKEN")
DB_PATH = os.getenv("DB_PATH", "lol_server.db")
WEB_PORT = int(os.getenv("PORT", "8080"))

# Recruitment channels (Discord channel IDs)
RECRUIT_CHANNELS = {
    "ノーマル・ARAM募集": 1569643108147265709,
    "デュオランク募集": 1569643437035229326,
    "フレックス募集": 1569643504999604285,
}
CUSTOM_CHANNEL_ID = 1567318455391101030
CUSTOM_ROLE_NAME = "@カスタム"
REGISTRATION_INFO_CHANNEL_ID = 1566055273146093599
TEAM_POINT_LIMIT = 16
MAX_DIAMOND = 2
MAX_MASTER = 1
ROLES = ["TOP", "JGL", "MID", "ADC", "SUP", "コーチ"]

RANK_DATA = {
    "CHALLENGER": {"pt": 8, "label": "Challenger (8pt)", "short": "Challenger", "color": discord.Color.red()},
    "GRANDMASTER": {"pt": 7, "label": "Grandmaster (7pt)", "short": "GM", "color": discord.Color.orange()},
    "MASTER": {"pt": 6, "label": "Master (6pt)", "short": "Master", "color": discord.Color.purple()},
    "DIAMOND_1_2": {"pt": 5, "label": "Diamond I-II (5pt)", "short": "D1-2", "color": discord.Color.blue()},
    "DIAMOND_3_4": {"pt": 4, "label": "Diamond III-IV (4pt)", "short": "D3-4", "color": discord.Color.blue()},
    "EMERALD_1_2": {"pt": 3, "label": "Emerald I-II (3pt)", "short": "E1-2", "color": discord.Color.green()},
    "EMERALD_3_4": {"pt": 2, "label": "Emerald III-IV (2pt)", "short": "E3-4", "color": discord.Color.green()},
    "PLATINUM": {"pt": 1, "label": "Platinum (1pt)", "short": "Plat", "color": discord.Color.gold()},
    "COACH": {"pt": 0, "label": "コーチ (0pt)", "short": "Coach", "color": discord.Color.dark_grey()},
}

# ---------- Database ----------
def db():
    return sqlite3.connect(DB_PATH)

def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                discord_id INTEGER PRIMARY KEY,
                riot_id TEXT NOT NULL,
                puuid TEXT,
                peak_rank TEXT NOT NULL,
                points INTEGER NOT NULL,
                main_role TEXT NOT NULL,
                champions TEXT,
                status TEXT DEFAULT 'FA'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recruit_threads (
                message_id INTEGER PRIMARY KEY,
                thread_id INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS join_button_threads (
                button_message_id INTEGER PRIMARY KEY,
                thread_id INTEGER NOT NULL,
                source_message_id INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recruitment_members (
                message_id INTEGER NOT NULL,
                discord_id INTEGER NOT NULL,
                PRIMARY KEY(message_id, discord_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                team_name TEXT PRIMARY KEY,
                leader_id INTEGER,
                member_ids TEXT,
                coach_id INTEGER,
                total_points INTEGER
            )
        """)

def get_player(discord_id):
    with db() as conn:
        return conn.execute(
            "SELECT riot_id, puuid, peak_rank, points, main_role, champions, status FROM players WHERE discord_id=?",
            (discord_id,)
        ).fetchone()

def rank_options():
    return [discord.SelectOption(label=v["label"], value=k) for k, v in RANK_DATA.items()]

# ---------- Flask keep-alive ----------
web_app = Flask("nexus-league-bot")

@web_app.get("/")
def home():
    return "Nexus League Bot is running!"

def start_web():
    # Disable the reloader so it does not start a second process/thread.
    web_app.run(host="0.0.0.0", port=WEB_PORT, use_reloader=False)

# ---------- Bot ----------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.reactions = True

class NexusBot(commands.Bot):
    async def setup_hook(self):
        # Persistent views: their buttons continue working after a restart.
        self.add_view(MainView())
        self.add_view(CustomPanelTriggerView())
        self.add_view(JoinThreadButtonView())
        for kind in RECRUIT_CHANNELS:
            self.add_view(RecruitmentView(kind))
        try:
            synced = await self.tree.sync()
            print(f"Slash commands synced: {len(synced)}")
        except Exception as exc:
            print(f"Slash command sync failed: {exc}")

bot = NexusBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

# ---------- Player registration ----------
class PlayerModal(discord.ui.Modal, title="Riot ID連携・プレイヤー登録"):
    riot = discord.ui.TextInput(label="Riot ID (例: Name#JP1)", placeholder="名前#タグ", required=True, max_length=100)
    role = discord.ui.TextInput(label="メインロール", placeholder="TOP / JGL / MID / ADC / SUP / コーチ", required=True, max_length=20)
    champ = discord.ui.TextInput(label="自己PR・得意チャンプ", style=discord.TextStyle.paragraph, required=False, max_length=800)

    def __init__(self, rank_key):
        super().__init__()
        self.rank_key = rank_key

    async def on_submit(self, interaction: discord.Interaction):
        riot_id = self.riot.value.strip()
        if "#" not in riot_id or not all(riot_id.split("#", 1)):
            await interaction.response.send_message("❌ Riot IDは `名前#タグ` の形式で入力してください。", ephemeral=True)
            return

        role = self.role.value.strip().upper()
        if role not in ROLES:
            await interaction.response.send_message(
                "❌ ロールは TOP / JGL / MID / ADC / SUP / コーチ のいずれかで入力してください。",
                ephemeral=True
            )
            return

        info = RANK_DATA[self.rank_key]
        with db() as conn:
            conn.execute("""
                INSERT INTO players(discord_id, riot_id, puuid, peak_rank, points, main_role, champions, status)
                VALUES (?, ?, NULL, ?, ?, ?, ?, 'FA')
                ON CONFLICT(discord_id) DO UPDATE SET
                    riot_id=excluded.riot_id, peak_rank=excluded.peak_rank,
                    points=excluded.points, main_role=excluded.main_role,
                    champions=excluded.champions, status='FA'
            """, (interaction.user.id, riot_id, self.rank_key, info["pt"], role, self.champ.value.strip()))

        game_name = riot_id.split("#", 1)[0]
        nickname = f"{game_name} / {role} / {info['short']}"[:32]
        nickname_changed = False
        if isinstance(interaction.user, discord.Member):
            try:
                await interaction.user.edit(nick=nickname, reason="Nexus League player registration")
                nickname_changed = True
            except discord.Forbidden:
                pass
            except discord.HTTPException:
                pass

        await interaction.response.send_message(
            f"✅ 登録しました！\nRiot ID: `{riot_id}`\nランク: **{info['label']}** / ロール: **{role}**"
            + (f"\nDiscord表示名: `{nickname}`" if nickname_changed else "\n※ Botの権限上、表示名は変更できませんでした。"),
            ephemeral=True
        )

        # Registration details are sent to the designated channel by ID.
        if interaction.guild:
            target = interaction.guild.get_channel(REGISTRATION_INFO_CHANNEL_ID)
            if target is None:
                try:
                    target = await interaction.guild.fetch_channel(REGISTRATION_INFO_CHANNEL_ID)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    target = None
            if target:
                opgg = f"https://www.op.gg/summoners/jp/{quote(riot_id.replace('#', '-'), safe='')}"
                embed = discord.Embed(title="📝 新規プレイヤー登録・確認", color=info["color"])
                embed.description = f"{interaction.user.mention} が登録しました。"
                embed.add_field(name="🎮 Riot ID", value=f"[{riot_id}]({opgg})", inline=True)
                embed.add_field(name="🏆 ランク", value=info["label"], inline=True)
                embed.add_field(name="⚔️ ロール", value=role, inline=True)
                embed.add_field(name="💬 自己PR", value=self.champ.value.strip() or "なし", inline=False)
                try:
                    await target.send(embed=embed)
                except discord.HTTPException:
                    pass

class PlayerSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="最高ランクまたはコーチを選択", options=rank_options(), min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PlayerModal(self.values[0]))

class PlayerSelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(PlayerSelect())

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎮 Riot IDを連携・登録する", style=discord.ButtonStyle.success, custom_id="nexus:register")
    async def register(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "👇 最高ランク（またはコーチ）を選択してください：",
            view=PlayerSelView(), ephemeral=True
        )

# ---------- FA card ----------
class FaModal(discord.ui.Modal, title="FA選手カード作成"):
    riot = discord.ui.TextInput(label="Riot ID", placeholder="名前#タグ", required=True)
    role = discord.ui.TextInput(label="メインロール", placeholder="TOP / JGL / MID / ADC / SUP / コーチ", required=True)
    rank = discord.ui.TextInput(label="ランク", placeholder="例: Diamond I / Master", required=True)
    intro = discord.ui.TextInput(label="自己PR・得意チャンプ", style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        riot_id = self.riot.value.strip()
        if "#" not in riot_id:
            await interaction.response.send_message("❌ Riot IDは `名前#タグ` の形式で入力してください。", ephemeral=True)
            return
        opgg = f"https://www.op.gg/summoners/jp/{quote(riot_id.replace('#', '-'), safe='')}"
        embed = discord.Embed(title="📝 FA選手募集", color=discord.Color.blurple())
        embed.set_author(name=f"{riot_id.split('#')[0]} / {self.role.value} / {self.rank.value}",
                         icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="🎮 Riot ID", value=f"[{riot_id}]({opgg})", inline=True)
        embed.add_field(name="🏆 ランク", value=self.rank.value, inline=True)
        embed.add_field(name="⚔️ ロール", value=self.role.value, inline=True)
        embed.add_field(name="💬 自己PR", value=self.intro.value.strip() or "未記入", inline=False)
        await interaction.response.send_message("✅ FAカードを投稿しました。", ephemeral=True)
        await interaction.channel.send(embed=embed)

class FaSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="登録ランクを選択（FAカード用）", options=rank_options())

    async def callback(self, interaction: discord.Interaction):
        # Keep rank selection in the modal's rank field as a readable label.
        await interaction.response.send_modal(FaModal())

class FaPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 FA選手カードを作成", style=discord.ButtonStyle.primary, custom_id="nexus:fa")
    async def open_fa(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FaModal())

# ---------- Auto recruitment post -> thread + join button ----------
class JoinThreadButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🙋 参加する", style=discord.ButtonStyle.success, custom_id="nexus:join_auto_thread")
    async def join_thread(self, interaction: discord.Interaction, button: discord.ui.Button):
        with db() as conn:
            row = conn.execute(
                "SELECT thread_id FROM join_button_threads WHERE button_message_id=?",
                (interaction.message.id,)
            ).fetchone()
        if not row:
            await interaction.response.send_message("募集スレッド情報が見つかりません。募集主に再投稿をお願いしてください。", ephemeral=True)
            return
        thread_id = row[0]
        thread = interaction.guild.get_thread(thread_id) if interaction.guild else None
        if thread is None and interaction.guild:
            try:
                thread = await interaction.guild.fetch_channel(thread_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                thread = None
        if thread is None:
            await interaction.response.send_message("スレッドが見つかりません。募集主に再投稿をお願いしてください。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await thread.add_user(interaction.user)
            with db() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO recruitment_members(message_id, discord_id) VALUES (?, ?)",
                    (interaction.message.id, interaction.user.id)
                )
            await thread.send(f"🙋 {interaction.user.mention} さんが参加します！")
            await interaction.followup.send(f"参加しました！ {thread.mention}", ephemeral=True)
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(f"Join thread error: {exc}")
            await interaction.followup.send(f"スレッドへの参加に失敗しました。権限を確認してください。\n{thread.mention}", ephemeral=True)

@bot.event
async def on_message(message: discord.Message):
    # Users can simply post "ノマ@4" / "ランク@2" in one of the three recruitment channels.
    if message.author.bot or message.channel.id not in RECRUIT_CHANNELS.values():
        await bot.process_commands(message)
        return
    kind = next((name for name, channel_id in RECRUIT_CHANNELS.items() if channel_id == message.channel.id), "募集")
    try:
        thread = await message.create_thread(
            name=f"🎮┃{message.author.display_name}┃{message.content[:45]}"[:100],
            auto_archive_duration=1440
        )
        await thread.send(f"📣 {message.author.mention} さんが募集を開始しました！\n**募集内容：** {message.content}")
        button_message = await message.reply(
            f"募集主：{message.author.mention} ｜ **{kind}**\n参加する方は下のボタンを押してください。",
            view=JoinThreadButtonView(),
            mention_author=False
        )
        with db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO recruit_threads(message_id, thread_id) VALUES (?, ?)",
                (message.id, thread.id)
            )
            conn.execute(
                "INSERT OR REPLACE INTO join_button_threads(button_message_id, thread_id, source_message_id) VALUES (?, ?, ?)",
                (button_message.id, thread.id, message.id)
            )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"Auto recruitment thread creation failed for message {message.id}: {exc}")
        try:
            await message.reply("⚠️ スレッドを作成できませんでした。Botの権限（スレッド作成・メッセージ送信）を確認してください。", mention_author=False)
        except discord.HTTPException:
            pass
    await bot.process_commands(message)

# ---------- Fixed-channel recruitment buttons ----------
class RecruitmentView(discord.ui.View):
    def __init__(self, kind: str):
        super().__init__(timeout=None)
        self.kind = kind
        # custom_id must be stable for persistent views
        button = discord.ui.Button(
            label="🙋 参加する（スレッド作成・参加）",
            style=discord.ButtonStyle.success,
            custom_id=f"nexus:join:{kind}"
        )
        button.callback = self.join_recruitment
        self.add_item(button)

    async def join_recruitment(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("サーバー内の募集チャンネルで操作してください。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        # One thread per panel message; create it on first click, reuse afterwards.
        with db() as conn:
            row = conn.execute("SELECT thread_id FROM recruit_threads WHERE message_id=?",
                              (interaction.message.id,)).fetchone()
        thread = interaction.guild.get_thread(row[0]) if row else None
        if row and thread is None:
            try:
                thread = await interaction.guild.fetch_channel(row[0])
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                thread = None
        if thread is None:
            try:
                thread = await interaction.message.create_thread(
                    name=f"🎮┃{self.kind}"[:100], auto_archive_duration=1440
                )
                await thread.send(f"🧵 **{self.kind}** の募集スレッドです。参加者はこちらで相談してください。")
                with db() as conn:
                    conn.execute("INSERT OR REPLACE INTO recruit_threads(message_id, thread_id) VALUES (?, ?)",
                                 (interaction.message.id, thread.id))
            except (discord.Forbidden, discord.HTTPException) as exc:
                print(f"Recruit thread creation failed: {exc}")
                await interaction.followup.send("スレッドを作成できませんでした。Botの権限を確認してください。", ephemeral=True)
                return
        try:
            await thread.add_user(interaction.user)
            with db() as conn:
                conn.execute("INSERT OR IGNORE INTO recruitment_members(message_id, discord_id) VALUES (?, ?)",
                             (interaction.message.id, interaction.user.id))
            await thread.send(f"🙋 {interaction.user.mention} が参加しました。")
            await interaction.followup.send(f"参加しました！こちらです：{thread.mention}", ephemeral=True)
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(f"Could not add member to recruitment thread: {exc}")
            await interaction.followup.send(f"スレッドは作成済みです：{thread.mention}\nBotにスレッド参加者追加権限がない可能性があります。", ephemeral=True)

# ---------- Custom recruitment ----------
class CustomCreateModal(discord.ui.Modal, title="カスタム・イベント募集設定"):
    title_input = discord.ui.TextInput(label="募集タイトル", placeholder="ワイワイカスタム / ノーマル募集", required=True, max_length=80)
    date_input = discord.ui.TextInput(label="日程", placeholder="11月4日", required=True, max_length=50)
    time_input = discord.ui.TextInput(label="時間", placeholder="21:00〜", required=True, max_length=50)
    note_input = discord.ui.TextInput(label="補足（任意）", required=False, style=discord.TextStyle.paragraph, max_length=500)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("サーバーのテキストチャンネルで実行してください。", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🎮 {self.title_input.value}",
            description=(
                f"**📅 日程:** {self.date_input.value}\n"
                f"**⏰ 時間:** {self.time_input.value}\n"
                f"**📝 補足:** {self.note_input.value.strip() or 'なし'}\n\n"
                "👇 参加する方は下の **✅** を押してください。参加者は専用スレッドへ招待されます。"
            ),
            color=discord.Color.blue()
        )
        await interaction.response.send_message("募集を作成しています…", ephemeral=True)
        custom_role = discord.utils.get(interaction.guild.roles, name=CUSTOM_ROLE_NAME.lstrip("@"))
        role_mention = custom_role.mention if custom_role else "@カスタム（ロール未設定）"
        msg = await interaction.channel.send(
            content=f"{role_mention} 新しいカスタム募集です！",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=[custom_role] if custom_role else [], users=False, everyone=False)
        )
        await msg.add_reaction("✅")

        try:
            thread = await msg.create_thread(
                name=f"🎮┃{self.title_input.value} ({self.date_input.value})"[:100],
                auto_archive_duration=1440
            )
            await thread.send("🧵 専用スレッドです。作戦会議や通話の相談に使ってください！")
            with db() as conn:
                conn.execute("INSERT OR REPLACE INTO recruit_threads(message_id, thread_id) VALUES (?, ?)",
                             (msg.id, thread.id))
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(f"Thread creation failed: {exc}")

class CustomPanelTriggerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📅 新規募集パネルを立てる", style=discord.ButtonStyle.blurple, custom_id="nexus:custom_panel")
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CustomCreateModal())

# ---------- Reactions: add users to recruitment thread ----------
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if bot.user and payload.user_id == bot.user.id:
        return
    if str(payload.emoji) not in ("✅", "☑️"):
        return
    with db() as conn:
        row = conn.execute("SELECT thread_id FROM recruit_threads WHERE message_id=?",
                           (payload.message_id,)).fetchone()
    if not row:
        return

    guild = bot.get_guild(payload.guild_id) if payload.guild_id else None
    if not guild:
        return
    thread = guild.get_thread(row[0])
    if thread is None:
        try:
            thread = await guild.fetch_channel(row[0])
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
    try:
        member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        await thread.add_user(member)
        with db() as conn:
            conn.execute("INSERT OR IGNORE INTO recruitment_members(message_id, discord_id) VALUES (?, ?)",
                         (payload.message_id, payload.user_id))
        try:
            await thread.send(f"✅ {member.mention} が参加しました。")
        except discord.HTTPException:
            pass
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"Could not add reaction user to thread: {exc}")

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if str(payload.emoji) not in ("✅", "☑️"):
        return
    with db() as conn:
        row = conn.execute("SELECT thread_id FROM recruit_threads WHERE message_id=?",
                           (payload.message_id,)).fetchone()
        conn.execute("DELETE FROM recruitment_members WHERE message_id=? AND discord_id=?",
                    (payload.message_id, payload.user_id))
    if not row or not payload.guild_id:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    thread = guild.get_thread(row[0])
    if thread:
        try:
            member = guild.get_member(payload.user_id)
            if member:
                await thread.remove_user(member)
        except (discord.Forbidden, discord.HTTPException):
            pass

# ---------- Slash commands ----------
@bot.tree.command(name="setup", description="プレイヤー登録パネルを設置（管理者）")
@app_commands.checks.has_permissions(administrator=True)
async def setup_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎮 Nexus League - プレイヤー登録",
        description="ボタンからRiot ID・最高ランク・メインロール・自己PRを登録してください。",
        color=discord.Color.green()
    )
    await interaction.channel.send(embed=embed, view=MainView())
    await interaction.response.send_message("✅ 登録パネルを設置しました。", ephemeral=True)

@bot.tree.command(name="fa_panel", description="FA選手カード作成パネルを設置（管理者）")
@app_commands.checks.has_permissions(administrator=True)
async def fa_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="📝 FA選手カード作成", description="ボタンからFAカードを作成できます。", color=discord.Color.blurple())
    await interaction.channel.send(embed=embed, view=FaPanelView())
    await interaction.response.send_message("✅ FAパネルを設置しました。", ephemeral=True)

@bot.tree.command(name="custom_panel", description="カスタム募集パネルを設置（管理者）")
@app_commands.checks.has_permissions(administrator=True)
async def custom_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="📅 カスタム・イベント募集", description="ボタンから新しい募集を作成できます。", color=discord.Color.blue())
    await interaction.channel.send(embed=embed, view=CustomPanelTriggerView())
    await interaction.response.send_message("✅ カスタム募集パネルを設置しました。", ephemeral=True)

@bot.tree.command(name="setup_recruitments", description="指定チャンネルに募集参加パネルを設置（管理者）")
@app_commands.checks.has_permissions(administrator=True)
async def setup_recruitments(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    results = []
    for kind, channel_id in RECRUIT_CHANNELS.items():
        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            results.append(f"❌ {kind}: チャンネルが見つかりません ({channel_id})")
            continue
        embed = discord.Embed(
            title=f"🎮 {kind}",
            description="下の **参加する** ボタンを押すと専用スレッドが作成（既存スレッドがあれば再利用）され、参加できます。",
            color=discord.Color.green()
        )
        try:
            await channel.send(embed=embed, view=RecruitmentView(kind))
            results.append(f"✅ {kind}: 設置完了")
        except discord.HTTPException as exc:
            results.append(f"❌ {kind}: {exc}")
    custom_channel = interaction.guild.get_channel(CUSTOM_CHANNEL_ID)
    if isinstance(custom_channel, discord.TextChannel):
        role = discord.utils.get(interaction.guild.roles, name=CUSTOM_ROLE_NAME.lstrip("@"))
        mention = role.mention if role else "@カスタム（ロール未検出）"
        try:
            await custom_channel.send(
                f"{mention} カスタム募集はこちらから作成してください。",
                embed=discord.Embed(title="🛠️ カスタム募集作成", description="ボタンから日時・タイトルを入力して募集を立てられます。", color=discord.Color.blurple()),
                view=CustomPanelTriggerView(),
                allowed_mentions=discord.AllowedMentions(roles=[role] if role else [], users=False, everyone=False)
            )
            results.append("✅ カスタム募集チャンネル: 設置完了（@カスタムロールのみ通知）")
        except discord.HTTPException as exc:
            results.append(f"❌ カスタム募集チャンネル: {exc}")
    else:
        results.append(f"❌ カスタム募集チャンネルが見つかりません ({CUSTOM_CHANNEL_ID})")
    await interaction.followup.send("\\n".join(results), ephemeral=True)

@bot.tree.command(name="profile", description="自分の登録情報を確認")
async def profile(interaction: discord.Interaction):
    row = get_player(interaction.user.id)
    if not row:
        await interaction.response.send_message("まだ登録されていません。`/setup` のパネルから登録してください。", ephemeral=True)
        return
    riot_id, puuid, rank_key, points, role, champions, status = row
    info = RANK_DATA.get(rank_key, {"label": rank_key, "color": discord.Color.greyple()})
    embed = discord.Embed(title="👤 登録プロフィール", color=info["color"])
    embed.add_field(name="Riot ID", value=riot_id, inline=True)
    embed.add_field(name="ランク", value=info["label"], inline=True)
    embed.add_field(name="ポイント", value=str(points), inline=True)
    embed.add_field(name="メインロール", value=role, inline=True)
    embed.add_field(name="自己PR", value=champions or "なし", inline=False)
    embed.add_field(name="状態", value=status, inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="players", description="登録済みプレイヤー一覧")
async def players(interaction: discord.Interaction):
    with db() as conn:
        rows = conn.execute("SELECT discord_id, riot_id, peak_rank, points, main_role FROM players ORDER BY points DESC, riot_id").fetchall()
    if not rows:
        await interaction.response.send_message("登録プレイヤーはいません。", ephemeral=True)
        return
    lines = []
    for discord_id, riot_id, rank_key, points, role in rows[:25]:
        rank_label = RANK_DATA.get(rank_key, {}).get("label", rank_key)
        lines.append(f"<@{discord_id}> — **{riot_id}** / {role} / {rank_label} ({points}pt)")
    embed = discord.Embed(title=f"👥 登録プレイヤー一覧 ({len(rows)}人)", description="\\n".join(lines), color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        message = "❌ このコマンドはサーバー管理者のみ実行できます。"
    else:
        print(f"App command error: {error}")
        message = "❌ コマンド実行中にエラーが発生しました。Botログを確認してください。"
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)

# ---------- Entrypoint ----------
if __name__ == "__main__":
    init_db()
    threading.Thread(target=start_web, daemon=True).start()
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN が設定されていません。環境変数にBot Tokenを設定してください。")
    bot.run(TOKEN)
