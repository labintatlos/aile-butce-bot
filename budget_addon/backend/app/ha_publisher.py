"""Sensör değerlerinin Home Assistant'a yazılması.

Yol olarak MQTT değil **Supervisor üzerinden Home Assistant REST API'si**
seçildi. Gerekçesi: MQTT ayrı bir aracı eklentinin kurulu olmasını şart
koşardı ve yeni bir Python bağımlılığı getirirdi; oysa eklenti Supervisor'ın
verdiği belirteçle Home Assistant'a zaten konuşabilir. HTTP istemcisi olarak
aiogram'ın getirdiği `aiohttp` kullanılır, yani yeni bir paket eklenmez.

Bu yolla yazılan sensörler Home Assistant yeniden başlatıldığında kaybolur.
Sorun değildir: yayımlayıcı belirli aralıklarla çalışır ve değerleri yeniden
yazar. Kaybolan bir değer en fazla bir aralık boyunca eksik kalır.

Yayımlama **asla uygulamayı düşürmez**. Home Assistant erişilemezse hata
loglanır ve bir sonraki turda yeniden denenir; bütçe kaydı bundan etkilenmez.
"""

from __future__ import annotations

import asyncio
import logging

from .config import Settings
from .services import ha_state

logger = logging.getLogger(__name__)

SUPERVISOR_STATE_URL = "http://supervisor/core/api/states/{entity_id}"
REQUEST_TIMEOUT_SECONDS = 10


async def publish_once(settings: Settings, session_factory, *, client=None) -> int:
    """Bütün sensörleri bir kez yazar ve başarılı yazma sayısını döner."""
    if not settings.supervisor_token:
        return 0

    async with session_factory() as session:
        sensors = await ha_state.collect(session, timezone=settings.timezone)

    owns_client = client is None
    if owns_client:
        import aiohttp

        client = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        )

    headers = {
        "Authorization": f"Bearer {settings.supervisor_token}",
        "Content-Type": "application/json",
    }

    written = 0
    try:
        for sensor in sensors:
            url = SUPERVISOR_STATE_URL.format(entity_id=sensor.entity_id)
            try:
                async with client.post(
                    url, json=sensor.payload(), headers=headers
                ) as response:
                    if response.status >= 400:
                        logger.warning(
                            "Home Assistant %s sensörünü kabul etmedi (HTTP %s)",
                            sensor.entity_id,
                            response.status,
                        )
                        continue
                written += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "Home Assistant'a yazılamadı: %s", sensor.entity_id, exc_info=True
                )
    finally:
        if owns_client:
            await client.close()
    return written


async def run_publisher(settings: Settings, session_factory) -> None:
    """Sensörleri düzenli aralıklarla yazar."""
    interval = max(settings.ha_publish_interval_minutes, 1) * 60
    logger.info(
        "Home Assistant sensörleri her %d dakikada bir yayımlanacak",
        settings.ha_publish_interval_minutes,
    )
    while True:
        try:
            written = await publish_once(settings, session_factory)
            logger.debug("%d sensör yayımlandı", written)
        except asyncio.CancelledError:
            logger.info("Home Assistant yayımlayıcısı durduruldu")
            raise
        except Exception:
            # Yayimlayici, tek bir hatali turda olmemelidir: bir sonraki turda
            # yeniden denemek, sensorleri tamamen kaybetmekten iyidir.
            logger.exception("Sensör yayımlanırken beklenmedik hata")
        await asyncio.sleep(interval)


def start_publisher_task(settings: Settings, session_factory) -> asyncio.Task | None:
    """Yayımlayıcıyı başlatır. Kapalıysa veya belirteç yoksa sessizce atlanır."""
    if not settings.publish_ha_sensors:
        return None
    if not settings.supervisor_token:
        logger.info(
            "Supervisor belirteci yok; Home Assistant sensörleri yayımlanmayacak. "
            "Eklenti dışında çalışırken bu beklenen durumdur."
        )
        return None
    return asyncio.create_task(run_publisher(settings, session_factory))
