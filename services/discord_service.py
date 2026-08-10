import logging
import os

from dotenv import load_dotenv

from services.notifications import embeds
from services.notifications.discord_transport import DiscordTransport
from services.notifications.engine import NotificationEngine

load_dotenv()

logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_PICKS = os.getenv("DISCORD_CHANNEL_PICKS", "")
DISCORD_CHANNEL_RESULTS = os.getenv("DISCORD_CHANNEL_RESULTS", "")
DISCORD_CHANNEL_MODEL_OUTPUT = os.getenv("DISCORD_CHANNEL_MODEL_OUTPUT", "")
DISCORD_CHANNEL_MODEL_SUMMARY = os.getenv("DISCORD_CHANNEL_MODEL_SUMMARY", "")


DISCORD_CHANNEL_HEALTH = os.getenv("DISCORD_CHANNEL_HEALTH", DISCORD_CHANNEL_RESULTS)


_engine = NotificationEngine()
_engine.register_channel(
"picks", DiscordTransport(DISCORD_BOT_TOKEN, DISCORD_CHANNEL_PICKS, name="discord:picks")
)
_engine.register_channel(
"results", DiscordTransport(DISCORD_BOT_TOKEN, DISCORD_CHANNEL_RESULTS, name="discord:results")
)
_engine.register_channel(
"health", DiscordTransport(DISCORD_BOT_TOKEN, DISCORD_CHANNEL_HEALTH, name="discord:health")
)


_engine.register_channel(
"model_output",
    DiscordTransport(DISCORD_BOT_TOKEN, DISCORD_CHANNEL_MODEL_OUTPUT, name="discord:model_output"),
)
_engine.register_channel(
"model_summary",
    DiscordTransport(
        DISCORD_BOT_TOKEN, DISCORD_CHANNEL_MODEL_SUMMARY, name="discord:model_summary"
    ),
)


def is_enabled() -> bool:

    return bool(DISCORD_BOT_TOKEN)


def send_pick(pick: dict) -> bool:

    try:
        return _engine.post_to_channel("picks", embed=embeds.build_pick_embed(pick))
    except Exception:
        logger.warning("discord_service.send_pick failed", exc_info=True)
        return False


def send_moneyline_output(data: dict) -> bool:

    try:
        return _engine.post_to_channel(
"model_output", embed=embeds.build_moneyline_output_embed(data)
        )
    except Exception:
        logger.warning("discord_service.send_moneyline_output failed", exc_info=True)
        return False


def send_totals_output(data: dict) -> bool:

    try:
        return _engine.post_to_channel("model_output", embed=embeds.build_totals_output_embed(data))
    except Exception:
        logger.warning("discord_service.send_totals_output failed", exc_info=True)
        return False


def send_model_output(data: dict) -> bool:

    try:
        pick_type = (data.get("pick_type") or "").lower()
        if pick_type == "totals":
            return send_totals_output(data)
        return send_moneyline_output(data)
    except Exception:
        logger.warning("discord_service.send_model_output failed", exc_info=True)
        return False


def send_results(result: dict) -> bool:

    try:
        return _engine.post_to_channel("results", embed=embeds.build_result_embed(result))
    except Exception:
        logger.warning("discord_service.send_results failed", exc_info=True)
        return False


def send_daily_summary(data: dict) -> bool:

    try:
        return _engine.post_to_channel("results", embed=embeds.build_daily_summary_embed(data))
    except Exception:
        logger.warning("discord_service.send_daily_summary failed", exc_info=True)
        return False


def send_model_health(report: dict) -> bool:

    try:
        return _engine.post_to_channel("health", embed=embeds.build_model_health_embed(report))
    except Exception:
        logger.warning("discord_service.send_model_health failed", exc_info=True)
        return False


def send_weekly_summary(data: dict) -> bool:

    try:
        return _engine.post_to_channel("results", embed=embeds.build_weekly_summary_embed(data))
    except Exception:
        logger.warning("discord_service.send_weekly_summary failed", exc_info=True)
        return False


def send_diagnostics(report: dict) -> bool:

    try:
        return _engine.post_to_channel("health", embed=embeds.build_diagnostics_embed(report))
    except Exception:
        logger.warning("discord_service.send_diagnostics failed", exc_info=True)
        return False


def send_daily_model_summary(report_text: str) -> bool:

    try:
        return _engine.post_to_channel("model_summary", content=report_text)
    except Exception:
        logger.warning("discord_service.send_daily_model_summary failed", exc_info=True)
        return False
