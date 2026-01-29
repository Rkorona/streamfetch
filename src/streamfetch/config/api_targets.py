import random
import logging
from streamfetch.config.settings import config  # 导入配置

logger = logging.getLogger("streamfetch")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://listen.tidal.com/",
}


def get_base_url():
    # 从配置中获取列表
    targets = config["network"]["api_urls"]
    if not targets:
        raise Exception("配置文件中未找到有效的 api_urls")

    url = random.choice(targets)
    logger.info(f"🚀 [bold cyan]连接服务器:[/bold cyan] {url}", extra={"markup": True})
    return url
