
# ============================================================
# Nexus BOT - 修正版
# Part 1 / 8 : 基本設定・共通機能
# ============================================================

import discord
from dotenv import load_dotenv

load_dotenv()
from discord.ext import commands
from discord import app_commands

import asyncio
import logging
import os
import re
import unicodedata
from urllib.parse import quote
from typing import Optional

# ============================================================
# ログ設定
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("NexusBOT")

# ============================================================
# BOT設定
# ============================================================

BOT_TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = 1566019287473193063
OWNER_ID = 1392895521433321502

# ============================================================
# チャンネル設定
# ============================================================

REGISTRATION_CHANNEL_ID = 1566023396544745613
INPUT_CHECK_CHANNEL_ID = 1566055273146093599

FA_CARD_CHANNEL_ID = 1567091839519948840

TOURNAMENT_CHANNEL_ID = 1566061702716329994

TEAM_APPLICATION_CATEGORY_ID = 1566028466397384854

NORMAL_RECRUIT_CHANNEL_ID = 1569643108147265709
RANK_RECRUIT_CHANNEL_ID = 1569643437035229326
FLEX_RECRUIT_CHANNEL_ID = 1569643504999604285

CUSTOM_PANEL_CHANNEL_ID = 1567318455391101030

ROLE_PANEL_CHANNEL_ID = 1569616670035681353

# ============================================================
# ロール設定
# ============================================================

NORMAL_ROLE_ID = 1569579116750049380
CUSTOM_ROLE_ID = 1569578833953427507
TOURNAMENT_ROLE_ID = 1569578720216358923
RANK_ROLE_ID = 1569578957236473876

SELECTABLE_ROLE_IDS = [
    NORMAL_ROLE_ID,
    CUSTOM_ROLE_ID,
    TOURNAMENT_ROLE_ID,
    RANK_ROLE_ID,
]

# ============================================================
# 選手ランク設定（ポイント制廃止・ランク帯で統一）
# ============================================================

RANK_CHOICES = [
    "Challenger",
    "Grandmaster",
    "Master",
    "Diamond",
    "Emerald",
    "Platinum",
]

RANK_COLORS = {
    "Challenger": 0xE74C3C,
    "Grandmaster": 0x9B59B6,
    "Master": 0x3498DB,
    "Diamond": 0x00BFFF,
    "Emerald": 0x2ECC71,
    "Platinum": 0x48C9B0,
    "Coach": 0x95A5A6,
}

MAIN_ROLE_CHOICES = [
    "TOP",
    "JG",
    "MID",
    "ADC",
    "SUP",
    "コーチ",
]

# 選手登録時に自動付与するポジションロール
POSITION_ROLE_IDS = {
    "TOP": 1566031441807155210,
    "JG": 1566031623181434900,
    "MID": 1566031700809613423,
    "ADC": 1566031772179763320,
    "SUP": 1566031834234753075,
    "コーチ": 1566029418843869276,
}

# 選手登録時に自動付与するランクロール
RANK_ROLE_IDS = {
    "Challenger": 1569577861323427860,
    "Grandmaster": 1569577673200762980,
    "Master": 1566031942267314310,
    "Diamond": 1566032052296613888,
    "Emerald": 1566032229493248050,
    "Platinum": 1566032393855311922,
}

# ニックネームに表示するランク略称
RANK_NICKNAME_LABELS = {
    "Platinum": "P",
    "Emerald": "E",
    "Diamond": "D",
    "Master": "M",
    "Grandmaster": "GM",
    "Challenger": "CH",
}

# ============================================================
# 希望ロール設定
# ============================================================

MAIN_ROLE_CHOICES = [
    "TOP",
    "JG",
    "MID",
    "ADC",
    "SUP",
    "コーチ",
]

# ============================================================
# 募集設定
# ============================================================

CUSTOM_RECRUIT_PER_LIST = 3

# ============================================================
# Embedカラー
# ============================================================

DEFAULT_COLOR = 0x5865F2
SUCCESS_COLOR = 0x2ECC71
ERROR_COLOR = 0xE74C3C
WARNING_COLOR = 0xF1C40F

# ============================================================
# 共通Embed作成
# ============================================================

def create_embed(
    title: str,
    description: str = "",
    color: int = DEFAULT_COLOR,
) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        color=color,
    )


def create_rank_embed(
    title: str,
    description: str,
    rank: str,
) -> discord.Embed:
    return create_embed(
        title,
        description,
        RANK_COLORS.get(rank, DEFAULT_COLOR),
    )


def success_embed(title: str, description: str = ""):
    return create_embed(
        f"✅ {title}",
        description,
        SUCCESS_COLOR,
    )


def error_embed(title: str, description: str = ""):
    return create_embed(
        f"❌ {title}",
        description,
        ERROR_COLOR,
    )


def warning_embed(title: str, description: str = ""):
    return create_embed(
        f"⚠️ {title}",
        description,
        WARNING_COLOR,
    )


# ============================================================
# 権限確認
# ============================================================

def is_owner(user: discord.abc.User) -> bool:
    return user.id == OWNER_ID


def can_manage_recruit(
    user: discord.abc.User,
    recruiter_id: int,
) -> bool:
    return user.id in (recruiter_id, OWNER_ID)

_HIDDEN_ID_PREFIX = "\u2063"
_HIDDEN_ID_ZERO = "\u200b"
_HIDDEN_ID_ONE = "\u200c"


def encode_hidden_user_id(user_id: int) -> str:
    return _HIDDEN_ID_PREFIX + "".join(
        _HIDDEN_ID_ONE if bit == "1" else _HIDDEN_ID_ZERO
        for bit in format(user_id, "064b")
    )


def decode_hidden_user_id(footer_text: str) -> Optional[int]:
    if footer_text.startswith(_HIDDEN_ID_PREFIX):
        encoded = footer_text[len(_HIDDEN_ID_PREFIX):]
        bits = "".join(
            "0" if char == _HIDDEN_ID_ZERO else "1"
            for char in encoded[:64]
            if char in (_HIDDEN_ID_ZERO, _HIDDEN_ID_ONE)
        )
        if len(bits) == 64:
            return int(bits, 2)
    match = re.search(r"Creator ID: (\d+)", footer_text)
    return int(match.group(1)) if match else None




def can_manage_participant(
    user: discord.abc.User,
    participant_id: int,
) -> bool:
    return user.id in (participant_id, OWNER_ID)


# ============================================================
# Riot ID・OP.GG関連
# ============================================================

def normalize_riot_id(riot_id: str) -> str:
    return unicodedata.normalize("NFKC", riot_id.strip())


def make_opgg_url(riot_id: str) -> Optional[str]:
    """
    Riot ID から OP.GG の URL を生成する。
    形式：プレイヤー名#タグ
    """

    riot_id = normalize_riot_id(riot_id)

    if "#" not in riot_id:
        return None

    game_name, tag_line = riot_id.rsplit("#", 1)

    game_name = game_name.strip()
    tag_line = tag_line.strip()

    if not game_name or not tag_line:
        return None

    region = "jp"
    encoded_name = quote(game_name, safe="")
    encoded_tag = quote(tag_line, safe="")

    return (
        f"https://www.op.gg/summoners/{region}/"
        f"{encoded_name}-{encoded_tag}"
    )


# ============================================================
# Discord BOT設定
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True


class NexusBot(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
        )

    async def setup_hook(self):

        logger.info("Nexus BOT 起動準備中")

        guild = discord.Object(id=GUILD_ID)

        # 古いグローバルコマンドを削除し、現在のコマンド定義は保持する
        global_commands = self.tree.get_commands()
        self.tree.clear_commands(guild=None)
        await self.tree.sync()
        for command in global_commands:
            self.tree.add_command(command)

        # このBOTを導入しているサーバーにだけコマンドを登録
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

        logger.info("スラッシュコマンド同期完了")

    async def on_ready(self):

        logger.info(f"ログイン成功: {self.user}")

        await self.change_presence(
            activity=discord.Game("Nexus Server")
        )


bot = NexusBot()

# ============================================================
# Part 1 終了
# 次は Part 2：選手登録機能
# ============================================================


# ============================================================
