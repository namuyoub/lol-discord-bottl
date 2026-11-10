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
        c.execute("INSERT