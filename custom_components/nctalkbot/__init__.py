"""The Nextcloud Talk Bot integration."""
from __future__ import annotations
import json
import logging

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL, CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_flow
from aiohttp.web import Request, Response

from .talk_bot import generate_signature, check_capability
from .const import DOMAIN, CONF_SHARED_SECRET, EVENT_RECEIVED

_LOGGER = logging.getLogger(__name__)


async def handle_webhook(
    hass: HomeAssistant, webhook_id: str, request: Request
) -> Response:
    """Handle webhook callback."""
    server = request.headers.get("X-NEXTCLOUD-TALK-BACKEND")
    if server is None:
        _LOGGER.error(
            "Received invalid data from Nextcloud. Missing header: %s",
            "X-NEXTCLOUD-TALK-BACKEND",
        )
        return Response(status=401)
    random = request.headers.get("X-NEXTCLOUD-TALK-RANDOM")
    if random is None:
        _LOGGER.error(
            "Received invalid data from Nextcloud. Missing header: %s",
            "X-NEXTCLOUD-TALK-RANDOM",
        )
        return Response(status=401)
    signature = request.headers.get("X-NEXTCLOUD-TALK-SIGNATURE")
    if signature is None:
        _LOGGER.error(
            "Received invalid data from Nextcloud. Missing header: %s",
            "X-NEXTCLOUD-TALK-SIGNATURE",
        )
        return Response(status=401)

    config = hass.data[DOMAIN]
    url = config[CONF_URL]
    secret = config[CONF_SHARED_SECRET]

    if url != server:
        _LOGGER.error(
            "Error validating server: %s / %s",
            url,
            server,
        )
        return Response(status=401)

    body = await request.text()
    digest = generate_signature(body, secret, random).hexdigest()

    if digest != signature:
        _LOGGER.error(
            "Error validating signature: %s / %s",
            digest,
            signature,
        )
        return Response(status=401)

    try:
        data = json.loads(body) if body else {}
    except ValueError:
        _LOGGER.error(
            "Data needs to be formatted as JSON: %s",
            body,
        )
        return Response(status=400)

    if not isinstance(data, dict):
        _LOGGER.error(
            "Data needs to be a dictionary: %s",
            data,
        )
        return Response(status=400)

    data["webhook_id"] = webhook_id
    hass.bus.async_fire(EVENT_RECEIVED, data)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the component."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN] = entry.data
    url = entry.data[CONF_URL]

    if not check_capability(url, "bots-v1"):
        _LOGGER.error("Nextcloud instance does not support bots")

    webhook.async_register(
        hass,
        DOMAIN,
        DOMAIN,
        entry.data[CONF_WEBHOOK_ID],
        handle_webhook,
        allowed_methods=["POST"],
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    return True


async_remove_entry = config_entry_flow.webhook_async_remove_entry
