"""Nexus BOT entry point. Feature code lives in cogs/."""
from bot_core import BOT_TOKEN, bot, logger

# Import modules to register slash commands, listeners and UI classes.
from cogs import registration, fa_card, tournament, team, recruitment, custom, roles
from cogs.registration import RegistrationStartView
from cogs.tournament import TournamentView
from cogs.team import TeamApplicationPanelView
from cogs.recruitment import RecruitmentView
from cogs.custom import CustomRecruitmentPanelView, CustomRecruitmentView
from cogs.roles import RolePanelView


def register_persistent_views():
    bot.add_view(RegistrationStartView())
    bot.add_view(TournamentView())
    bot.add_view(TeamApplicationPanelView())
    bot.add_view(RecruitmentView())
    bot.add_view(CustomRecruitmentPanelView())
    bot.add_view(CustomRecruitmentView())
    bot.add_view(RolePanelView())
    logger.info("永続ボタンを登録しました。")


if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.critical("DISCORD_TOKEN が設定されていません。")
        raise RuntimeError(
            "Bot-Hostingの環境変数にDISCORD_TOKENを設定してください。"
        )
    register_persistent_views()
    logger.info("Nexus BOTを起動します。")
    bot.run(BOT_TOKEN)
