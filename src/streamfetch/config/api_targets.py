import random
import logging
from streamfetch.config.settings import config

logger = logging.getLogger("streamfetch")

# 更新为较新的 Chrome User-Agent，防止被老旧规则拦截
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://listen.tidal.com/",
    "Origin": "https://listen.tidal.com",
}


def get_base_url():
    targets = config["network"]["api_urls"]
    if not targets:
        raise Exception("配置文件中未找到有效 api_urls")

    # 随机选择一个
    url = random.choice(targets)

    # 修改点：降级为 debug，不再刷屏
    logger.debug(f"🚀 选中服务器: {url}")
    return url
