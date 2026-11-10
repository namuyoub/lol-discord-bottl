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

SPREADSHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1DnzBEIyP6ss0aaz3-J0Gq8jppwD9ZmncTnTHsBq8K3g/export?format=csv"

RANK_DATA = {
    "CHALLENGER": {"pt": 8, "label": "Challenger (8pt)", "short": "Challenger", "color": discord.Color.red()},
    "GRANDMASTER": {"pt": 7, "label": "Grandmaster (7pt)", "short": "GM", "color": discord.Color.orange()},
    "MASTER": {"pt": 6, "label": "Master (6pt)", "short": "Master", "color": discord.Color.purple()},
    "DIAMOND_1_2": {"pt": 5, "label": "Diamond I-II (5pt)", "short": "D1-2", "color": discord.Color.blue()},
    "DIAMOND_3_4": {"pt": 4, "label": "Diamond III-IV (4pt)", "short": "D3-4", "color": discord.Color.blue()},
    "EMERALD_1_2": {"pt": 3, "label": "Emerald I-II (3pt)", "short": "E1-2", "color": discord.Color.green()},
    "EMERALD_3_4": {"pt": 2, "label": "Emerald III-IV (2pt)", "short": "E3-4", "color": discord.Color.green()},
    "PLATINUM": {"pt": 1, "label": "Platinum (1pt)", "short": "Platinum", "color": discord.Color.gold()},
    "COACH": {"pt": 0, "label": "コーチ (0pt)", "short": "Coach", "color": discord.Color.dark_grey()},
}

def init_db():
    conn = sqlite3.connect("lol_server.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS players (discord_id INTEGER PRIMARY KEY, riot_id TEXT, puuid TEXT, peak_rank TEXT, points INTEGER, main_role TEXT, champions TEXT, status TEXT DEFAULT 'FA')")
    c.execute("CREATE TABLE IF NOT EXISTS teams (team_name TEXT PRIMARY KEY, leader_id INTEGER, member_ids TEXT, coach_id INTEGER, total_points INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS activity_log (discord_id INTEGER, last_active TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS recruit_threads (message_id INTEGER PRIMARY KEY, thread_id INTEGER)")
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
                players[str(name).strip()] = {"point": point, "roles": roles, "rank": rank}
    except Exception as e:
        print(f"⚠️ スプレッドシート読み込みエラー: {e}")
    return players

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

class CustomCreateModal(discord.ui.Modal, title="カスタム・イベント募集設定"):
    title_input = discord.ui.TextInput(label="募集タイトル", placeholder="ワイワイカスタム / ノーマル募集", required=True)
    date_input = discord.ui.TextInput(label="日程", placeholder="11月4日", required=True)
    time_input = discord.ui.TextInput(label="時間", placeholder="21:00〜", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"🎮 {self.title_input.value}", 
            description=f"**📅 日程:** {self.date_input.value}\n**⏰ 時間:** {self.time_input.value}\n\n👇 参加される方は、下の **:sannka:** スタンプを押してください！自動で専用スレッドが作成され、参加メンバーに追加されます。", 
            color=discord.Color.blue()
        )
        
        msg = await interaction.channel.send(content="@everyone 新しい募集が開始されました！", embed=embed)
        
        try:
            sannka_emoji = discord.utils.get(interaction.guild.emojis, name="sannka")
            if sannka_emoji:
                await msg.add_reaction(sannka_emoji)
            else:
                await msg.add_reaction("✅")
        except:
            pass

        try:
            thread = await msg.create_thread(name=f"🎮┃{self.title_input.value} ({self.date_input.value})", auto_archive_duration=1440)
            await thread.send(f"🧵 専用スレッドを作成しました！このスレッド内でわちゃわちゃ作戦会議や通話のやり取りをしてください✨")
            
            conn = sqlite3.connect("lol_server.db")
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO recruit_threads VALUES (?, ?)", (msg.id, thread.id))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"スレッド作成エラー: {e}")

        await interaction.response.send_message("✅ 募集パネルと専用スレッドを作成しました！", ephemeral=True)

class CustomPanelTriggerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📅 新規募集パネルを立てる", style=discord.ButtonStyle.blurple, custom_id="trigger_custom_modal")
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response