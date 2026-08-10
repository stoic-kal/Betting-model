import logging

logger = logging.getLogger(__name__)


class NotificationEngine:
    def __init__(self):
        self._channels: dict[str, list] = {}

    def register_channel(self, channel_key: str, transport) -> None:

        self._channels.setdefault(channel_key, []).append(transport)

    def post_to_channel(self, channel_key: str, content: str = None, embed: dict = None) -> bool:

        transports = self._channels.get(channel_key)
        if not transports:
            logger.warning(
'notification engine: no transport registered for channel "%s".', channel_key
            )
            return False
        if content is None and embed is None:
            logger.warning(
'notification engine: post_to_channel("%s") called with no content or embed.',
                channel_key,
            )
            return False

        any_success = False
        for transport in transports:
            try:
                ok = (
                    transport.send_embed(embed)
                    if embed is not None
                    else transport.send_message(content)
                )
                any_success = any_success or ok
            except Exception:
                logger.warning(
'notification engine: unexpected error sending to "%s" via %s.',
                    channel_key,
                    getattr(transport, "name", transport.__class__.__name__),
                    exc_info=True,
                )
        return any_success
