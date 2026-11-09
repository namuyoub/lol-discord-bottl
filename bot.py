import os
from threading import Thread
import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import urllib.parse
import urllib.request
import csv
from flask import Flask

# --- Flask Keep Alive ---
app = Flask('')

@app.route('/')
def home():
    return 'Nexus League Bot is running!'

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

TEAM_POINT_LIMIT = 16
MAX_DIAMOND = 2
MAX_MASTER = 1
ROLES = ["TOP", "JGL", "MID", "ADC", "SUP"]

# --- スプレッドシートの「ウェブに公開(CSV)」のURL ---
SPREADSHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1DnzBEIyP6ss0aaz3-J0Gq8jppwD9ZmncTnTHsBq8K3g/export?format=csv"

RANK_DATA = {
    "CHALLENGER": {
        "pt": 8,
        "label": "Challenger (8pt)",
        "short": "Challenger",
        "color": discord.Color.red(),
    },
    "GRANDMASTER": {
        "pt": 7,
        "label": "Grandmaster (7pt)",
        "short": "GM",
        "color": discord.Color.orange(),
    },
    "MASTER": {
        "pt": 6,
        "label": "Master (6pt)",
        "short": "Master",
        "color": discord.Color.purple(),
    },
    "DIAMOND_1_2": {
        "pt": 5,
        "label": "Diamond I-II (5pt)",
        "short": "D1-2",
        "color": discord.Color.blue(),
    },
    "DIAMOND_3_4": {
        "pt": 4,
        "label": "Diamond III-IV (4pt)",
        "short": "D3-4",
        "color": discord.Color.blue(),
    },
    "EMERALD_1_2": {
        "pt": 3,
        "label": "Emerald I-II (3pt)",
        "short": "E1-2",
        "color": discord.Color.green(),
    },
    "EMERALD_3_4": {
        "pt": 2,
        "label": "Emerald III-IV (2pt)",
        "short": "E3-4",
        "color": discord.Color.green(),
    },
    "PLATINUM": {
        "pt": 1,
        "label": "Platinum (1pt)",
        "short": "Platinum",
        "color": discord.Color.gold(),
    },
    "COACH": {
        "pt": 0,
        "label": "コーチ (0pt)",
        "short": "Coach",
        "color": discord.Color.dark_grey(),
    },
}

def init_db():
    conn = sqlite3.connect("lol_server.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS players (discord_id INTEGER PRIMARY KEY, riot_id TEXT, puuid TEXT, peak_rank TEXT, points INTEGER, main_role TEXT, champions TEXT, status TEXT DEFAULT 'FA')")
    c.execute("CREATE TABLE IF NOT EXISTS teams (team_name TEXT PRIMARY KEY, leader_id INTEGER, member_ids TEXT, coach_id INTEGER, total_points INTEGER)")
    conn.commit()
    conn.close()

def load_players_from_sheet():
    players = {}
    try:
        req = urllib.request.Request(SPREADSHEET_CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            lines = [line.decode('utf-8') for line in response.readlines()]
            reader = csv.DictReader(lines)
            for row in reader:
                name = row.get("SN") or row.get("名前")
                if not name:
                    continue
                try:
                    point = int(row.get("ポイント", 0))
                except ValueError:
                    point = 0
                
                roles_str = row.get("希望ロール", "")
                roles = [r.strip().upper() for r in roles_str.split(",")] if roles_str else []
                rank = row.get("ランク", "")
                
                players[str(name).strip()] = {
                    "point": point,
                    "roles": roles,
                    "rank": rank
                }
    except Exception as e:
        print(f"⚠️ スプレッドシート読み込みエラー: {e}")
    return players

# --- 選手用登録モーダル（入力Checkへ転送） ---
class PlayerModal(discord.ui.Modal, title="Riot ID連携・プレイヤー登録"):
    riot = discord.ui.TextInput(label="Riot ID (例: Name#JP1)", placeholder="名前#タグ", required=True)
    role = discord.ui.TextInput(label="メインロール", placeholder="TOP / JG / MID / ADC / SUP / コーチ", required=True)
    champ = discord.ui.TextInput(label="自己PR・得意チャンプ", style=discord.TextStyle.paragraph, required=False)

    def __init__(self, rank):
        super().__init__()
        self.rank = rank

    async def on_submit(self, interaction: discord.Interaction):
        if "#" not in self.riot.value:
            await interaction.response.send_message("❌ `#` を含めた形式で入力してください。", ephemeral=True)
            return
        g_name, _ = self.riot.value.split("#", 1)
        info = RANK_DATA[self.rank]

        conn = sqlite3.connect("lol_server.db")
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO players VALUES (?, ?, ?, ?, ?, ?, ?, 'FA')",
                  (interaction.user.id, self.riot.value, "PUUID", self.rank, info["pt"], self.role.value, self.champ.value))
        conn.commit()
        conn.close()

        nick = f"{g_name} / {self.role.value} / {info['short']}"[:32]
        try:
            await interaction.user.edit(nick=nick)
        except:
            pass

        await interaction.response.send_message(f"✅ 登録完了！表示名を `{nick}` に変更しました。", ephemeral=True)

        target_ch = None
        for ch in interaction.guild.text_channels:
            if "入力check" in ch.name.lower() or "入力チェック" in ch.name.lower() or "1566055273146093599" in str(ch.id):
                target_ch = ch
                break

        if target_ch:
            opgg = f"https://www.op.gg/summoners/jp/{urllib.parse.quote(self.riot.value.replace('#', '-'))}"
            emb = discord.Embed(title="📝 新規プレイヤー登録・チェック用", description=f"{interaction.user.mention} が登録しました。", color=discord.Color.gold())
            emb.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            emb.add_field(name="🎮 Riot ID", value=f"[{self.riot.value}]({opgg})", inline=True)
            emb.add_field(name="🏆 ランク", value=info["label"], inline=True)
            emb.add_field(name="⚔️ ロール", value=self.role.value, inline=True)
            emb.add_field(name="💬 自己PR", value=self.champ.value or "なし", inline=False)
            await target_ch.send(embed=emb)

class PlayerSelect(discord.ui.Select):
    def __init__(self):
        opts = [discord.SelectOption(label=v["label"], value=k) for k, v in RANK_DATA.items()]
        super().__init__(placeholder="最高ランクまたはコーチを選択してください", options=opts)

    async def callback(self, interaction):
        await interaction.response.send_modal(PlayerModal(self.values[0]))

class PlayerSelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(PlayerSelect())

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎮 Riot IDを連携・登録する", style=discord.ButtonStyle.success, custom_id="reg_btn")
    async def reg(self, interaction, button):
        await interaction.response.send_message("👇 最高ランク（またはコーチ）を選択：", view=PlayerSelView(), ephemeral=True)

# --- 運営用手動FAカード投稿モーダル ---
class FaModal(discord.ui.Modal, title="FA選手カード作成（手動）"):
    riot = discord.ui.TextInput(label="Riot ID", placeholder="名前#タグ", required=True)
    role = discord.ui.TextInput(label="メインロール", placeholder="TOP / JG / MID / ADC / SUP", required=True)
    champ = discord.ui.TextInput(label="自己PR", style=discord.TextStyle.paragraph, required=False)

    def __init__(self, rank_key):
        super().__init__()
        self.rank_key = rank_key

    async def on_submit(self, interaction: discord.Interaction):
        info = RANK_DATA[self.rank_key]
        opgg = f"https://www.op.gg/summoners/jp/{urllib.parse.quote(self.riot.value.replace('#', '-'))}"
        emb = discord.Embed(title="📝 新規プレイヤー登録", description=f"{interaction.user.mention} が登録しました。", color=info["color"])
        emb.set_author(name=f"{self.riot.value.split('#')[0]} / {self.role.value} / {info['short']}", icon_url=interaction.user.display_avatar.url)
        emb.add_field(name="🎮 Riot ID", value=f"[{self.riot.value}]({opgg})", inline=True)
        emb.add_field(name="🏆 ランク", value=info["label"], inline=True)
        emb.add_field(name="⚔️ ロール", value=self.role.value, inline=True)
        await interaction.channel.send(embed=emb)
        await interaction.response.send_message("✅ FAカードを投稿しました！", ephemeral=True)

class FaSelect(discord.ui.Select):
    def __init__(self):
        opts = [discord.SelectOption(label=v["label"], value=k) for k, v in RANK_DATA.items()]
        super().__init__(placeholder="選手のランクを選択してください", options=opts)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(FaModal(self.values[0]))

class FaSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(FaSelect())

# --- カスタム参加管理ビュー ---
class CustomJoinView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="参加する", style=discord.ButtonStyle.green, custom_id="custom_join_btn")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        message = interaction.message
        embed = message.embeds[0]
        field_index = -1
        for i, field in enumerate(embed.fields):
            if "参加者一覧" in field.name:
                field_index = i
                break
        current_desc = embed.fields[field_index].value if field_index != -1 else "まだ参加者はいません。"
        participants = [] if current_desc == "まだ参加者はいません。" else current_desc.split("\n")
        user_mention = interaction.user.mention
        if user_mention not in participants:
            participants.append(user_mention)
        new_value = "\n".join(participants) if participants else "まだ参加者はいません。"
        count = len(participants)
        embed.set_field_at(field_index, name=f"参加者一覧 ({count}人)", value=new_value, inline=False)
        await message.edit(embed=embed)
        await interaction.response.send_message("✅ 参加を受け付けました！", ephemeral=True)

    @discord.ui.button(label="辞退する", style=discord.ButtonStyle.red, custom_id="custom_leave_btn")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        message = interaction.message
        embed = message.embeds[0]
        field_index = -1
        for i, field in enumerate(embed.fields):
            if "参加者一覧" in field.name:
                field_index = i
                break
        if field_index == -1:
            await interaction.response.send_message("❌ リストが見つかりません。", ephemeral=True)
            return
        current_desc = embed.fields[field_index].value
        participants = current_desc.split("\n") if current_desc != "まだ参加者はいません。" else []
        user_mention = interaction.user.mention
        if user_mention in participants:
            participants.remove(user_mention)
        new_value = "\n".join(participants) if participants else "まだ参加者はいません。"
        count = len(participants)
        embed.set_field_at(field_index, name=f"参加者一覧 ({count}人)", value=new_value, inline=False)
        await message.edit(embed=embed)
        await interaction.response.send_message("❌ 辞退しました。", ephemeral=True)

class CustomCreateModal(discord.ui.Modal, title="カスタム開催・詳細設定"):
    title_input = discord.ui.TextInput(label="カスタムタイトル", placeholder="ワイワイカスタム", required=True)
    date_input = discord.ui.TextInput(label="日程", placeholder="11月4日", required=True)
    time_input = discord.ui.TextInput(label="時間", placeholder="21:00〜", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title=f"🎮 {self.title_input.value}", description=f"**📅 日程:** {self.date_input.value}\n**⏰ 時間:** {self.time_input.value}", color=discord.Color.blue())
        embed.add_field(name="参加者一覧 (0人)", value="まだ参加者はいません。", inline=False)
        await interaction.channel.send(content="@everyone 新規カスタムの募集が開始されました！", embed=embed, view=CustomJoinView())
        await interaction.response.send_message("✅ パネルを作成しました！", ephemeral=True)

class CustomPanelTriggerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📅 新規カスタムを募集する", style=discord.ButtonStyle.blurple, custom_id="trigger_custom_modal")
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CustomCreateModal())

class TeamTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🚩 チーム結成を申請する", style=discord.ButtonStyle.green, custom_id="ticket_form_create")
    async def btn_create(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "結成")

    @discord.ui.button(label="🗑️ チーム解散を申請する", style=discord.ButtonStyle.red, custom_id="ticket_form_disband")
    async def btn_disband(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "解散")

    async def create_ticket(self, interaction: discord.Interaction, action_type: str):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user
        channel_name = f"{action_type}-{user.name}"
        if discord.utils.get(guild.text_channels, name=channel_name):
            await interaction.followup.send("⚠️ すでに専用チャンネルがあります。", ephemeral=True)
            return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)
        }
        try:
            ch = await guild.create_text_channel(name=channel_name, overwrites=overwrites)
            emb = discord.Embed(title=f"🏆 チーム{action_type}申請", description=f"{user.mention} さんようこそ！", color=discord.Color.green())
            await ch.send(embed=emb)
            await interaction.followup.send(f"✅ チャンネルを作成しました 👉 {ch.mention}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ エラー: {e}", ephemeral=True)

# --- マッチング検索用の名前入力モーダル ---
class MatchInputModal(discord.ui.Modal, title="チーム自動マッチング設定"):
    target_name = discord.ui.TextInput(label="軸にする選手名（スプレッドシートの表記）", placeholder="例: ふうこ", required=True)

    def __init__(self, preferred_roles):
        super().__init__()
        self.preferred_roles = preferred_roles

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        target_player_name = self.target_name.value.strip()
        players_db = load_players_from_sheet()

        target_player_data = None
        target_key = None
        for p_name in players_db:
            if target_player_name in p_name or p_name in target_player_name:
                target_key = p_name
                target_player_data = players_db[p_name]
                break

        if not target_player_data:
            await interaction.followup.send(f"スプレッドシートに「{target_player_name}」という名前が見つかりませんでした。", ephemeral=True)
            return

        author_point = target_player_data["point"]
        author_rank = target_player_data["rank"]

        matched_team = {}
        total_points = author_point
        diamond_count = 1 if "Diamond" in author_rank else 0
        master_count = 1 if "Master" in author_rank else 0
        
        assigned_roles = ROLES.copy()
        my_assigned_role = None
        for r in assigned_roles:
            if r not in self.preferred_roles:
                my_assigned_role = r
                break
        if not my_assigned_role:
                my_assigned_role = self.preferred_roles[0]

        matched_team[my_assigned_role] = (target_key, author_point)
        assigned_roles.remove(my_assigned_role)
        used_players = {target_key}

        success = True
        for target_role in assigned_roles:
            candidate_found = False
            for p_name, data in players_db.items():
                if p_name in used_players:
                    continue
                
                p_point = data["point"]
                p_rank = data["rank"]
                p_roles = data["roles"]

                if target_role in p_roles and len(p_roles) == 1 and target_role in self.preferred_roles:
                    continue

                is_diamond = "Diamond" in p_rank
                is_master = "Master" in p_rank

                if master_count > 0 and is_diamond:
                    continue
                if is_master and diamond_count > 0:
                    continue

                new_total = total_points + p_point
                new_diamond = diamond_count + (1 if is_diamond else 0)
                new_master = master_count + (1 if is_master else 0)

                if new_total <= TEAM_POINT_LIMIT and new_diamond <= MAX_DIAMOND and new_master <= MAX_MASTER:
                    matched_team[target_role] = (p_name, p_point)
                    total_points = new_total
                    diamond_count = new_diamond
                    master_count = new_master
                    used_players.add(p_name)
                    candidate_found = True
                    break
            
            if not candidate_found:
                success = False
                break

        if success and len(matched_team) == 5:
            embed = discord.Embed(title=f"自動マッチング結果（軸: {target_key}）", color=discord.Color.blue())
            embed.add_field(name="合計ポイント", value=f"{total_points}pt / {TEAM_POINT_LIMIT}pt", inline=False)
            for role in ROLES:
                p_name, p_pt = matched_team.get(role, ("未配置", 0))
                embed.add_field(name=role, value=f"{p_name} ({p_pt}pt)", inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"「{target_key}」を軸にした条件を満たす組み合わせが見つかりませんでした。", ephemeral=True)

class MatchRoleSelectView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=60)
        self.user = user

    @discord.ui.select(
        placeholder="今回希望するロールを選択してください（複数可）",
        min_values=1, max_values=3,
        options=[
            discord.SelectOption(label="TOP", value="TOP"),
            discord.SelectOption(label="JGL", value="JGL"),
            discord.SelectOption(label="MID", value="MID"),
            discord.SelectOption(label="ADC", value="ADC"),
            discord.SelectOption(label="SUP", value="SUP"),
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user != self.user:
            await interaction.response.send_message("他の人の選択です。", ephemeral=True)
            return
        modal = MatchInputModal(select.values)
        await interaction.response.send_modal(modal)
        self.stop()

# --- Bot 本体 & スラッシュコマンド ---
class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all(), max_messages=1000, chunk_guilds_at_startup=False)

    async def setup_hook(self):
        init_db()
        self.add_view(MainView())
        self.add_view(CustomJoinView())
        self.add_view(CustomPanelTriggerView())
        self.add_view(TeamTicketView())
        
        # サーバIDを設定
        MY_GUILD_ID = discord.Object(id=1569244463136637058)
        self.tree.copy_global_to(guild=MY_GUILD_ID)
        await self.tree.sync(guild=MY_GUILD_ID)
        print("コマンドを即時同期しました！")

bot = Bot()

# --- 管理人専用コマンド群（administrator=True） ---
@bot.tree.command(name="setup_panel", description="【管理】選手用RiotID連携パネルを設置")
@app_commands.checks.has_permissions(administrator=True)
async def setup_panel(interaction: discord.Interaction):
    emb = discord.Embed(title="Riot ID連携 ＆ プレイヤー登録", description="下のボタンから登録してください。", color=discord.Color.gold())
    await interaction.channel.send(embed=emb, view=MainView())
    await interaction.response.send_message("パネル設置完了！", ephemeral=True)

@bot.tree.command(name="fa_post", description="【管理】手動でFA選手のカードを投稿する")
@app_commands.checks.has_permissions(administrator=True)
async def fa_post(interaction: discord.Interaction):
    await interaction.response.send_message("追加する選手のランクを選択してください:", view=FaSelectView(), ephemeral=True)

@bot.tree.command(name="setup_custom", description="【管理】カスタム募集パネルを設置（@everyone通知付き）")
@app_commands.checks.has_permissions(administrator=True)
async def setup_custom(interaction: discord.Interaction):
    await interaction.channel.send("カスタム募集パネル", view=CustomPanelTriggerView())
    await interaction.response.send_message("設置完了！", ephemeral=True)

@bot.tree.command(name="setup_team", description="【管理】チーム申請パネルを設置")
@app_commands.checks.has_permissions(administrator=True)
async def setup_team(interaction: discord.Interaction):
    emb = discord.Embed(title="大会チーム申請", color=discord.Color.blue())
    await interaction.channel.send(embed=emb, view=TeamTicketView())
    await interaction.response.send_message("設置完了！", ephemeral=True)

@bot.tree.command(name="match", description="【管理】スプレッドシートから選手名を指定してチームを自動編成する")
@app_commands.checks.has_permissions(administrator=True)
async def match_slash(interaction: discord.Interaction):
    view = MatchRoleSelectView(interaction.user)
    await interaction.response.send_message("今回希望するロールを選択してください。", view=view, ephemeral=True)

if __name__ == "__main__":
    keep_alive()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("DISCORD_TOKENが設定されていません！")
    else:
        bot.run(token)