import logging
import time
import hashlib

import requests

from services.notifications.transport import NotificationTransport

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"
REQUEST_TIMEOUT_SECONDS = 5
MAX_RETRIES = 2
BACKOFF_BASE_SECONDS = 0.5
MESSAGE_CHAR_LIMIT = 2000


class DiscordTransport(NotificationTransport):

    def __init__(self, bot_token: str, channel_id: str, name: str = "discord"):
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.name = name

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.channel_id)

    def send_message(self, content: str, idempotency_key: str = None) -> bool:
        return self._post({"content": content[:MESSAGE_CHAR_LIMIT]}, idempotency_key)

    def send_embed(self, embed: dict, idempotency_key: str = None) -> bool:
        return self._post({"embeds": [embed]}, idempotency_key)

    def _post(self, payload: dict, idempotency_key: str = None) -> bool:
        if not self.is_configured():
            logger.warning(
"%s: not configured (missing token or channel_id), skipping send.", self.name
            )
            return False

        url = f"{DISCORD_API_BASE}/channels/{self.channel_id}/messages"
        if idempotency_key:
            # Discord de-duplicates repeated message creates carrying the same
            # nonce when enforce_nonce is true.  Keep the nonce stable across
            # worker crashes and transport retries.
            payload = dict(payload)
            payload["nonce"] = str(int(hashlib.sha256(idempotency_key.encode()).hexdigest()[:15], 16))
            payload["enforce_nonce"] = True
        headers = {
"Authorization": f"Bot {self.bot_token}",
"Content-Type": "application/json",
        }

        attempt = 0
        while attempt <= MAX_RETRIES:
            try:
                resp = requests.post(
                    url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS
                )

                if resp.status_code < 300:
                    return True

                if resp.status_code == 429:
                    wait = self._retry_after_seconds(resp)
                    logger.warning(
"%s: rate limited, waiting %.1fs (attempt %d/%d).",
                        self.name,
                        wait,
                        attempt + 1,
                        MAX_RETRIES + 1,
                    )
                    time.sleep(wait)
                    attempt += 1
                    continue

                if 500 <= resp.status_code < 600:
                    wait = BACKOFF_BASE_SECONDS * (2**attempt)
                    logger.warning(
"%s: server error %s, retrying in %.1fs (attempt %d/%d).",
                        self.name,
                        resp.status_code,
                        wait,
                        attempt + 1,
                        MAX_RETRIES + 1,
                    )
                    time.sleep(wait)
                    attempt += 1
                    continue

                logger.warning(
"%s: send failed permanently, status=%s body=%s",
                    self.name,
                    resp.status_code,
                    resp.text[:300],
                )
                return False

            except requests.RequestException:
                wait = BACKOFF_BASE_SECONDS * (2**attempt)
                logger.warning(
"%s: request error, retrying in %.1fs (attempt %d/%d)",
                    self.name,
                    wait,
                    attempt + 1,
                    MAX_RETRIES + 1,
                    exc_info=True,
                )
                time.sleep(wait)
                attempt += 1

        logger.warning("%s: send failed after %d attempts.", self.name, MAX_RETRIES + 1)
        return False

    @staticmethod
    def _retry_after_seconds(resp) -> float:
        try:
            return float(resp.json().get("retry_after", 1.0))
        except Exception:
            return 1.0
