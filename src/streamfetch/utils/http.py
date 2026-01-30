import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from streamfetch.config.api_targets import HEADERS
from streamfetch.config.settings import config  # 导入配置

_session = requests.Session()

# 从配置读取重试次数
retries_count = config["network"]["max_retries"]
# concurrency = config["network"]["concurrency"]
retries = Retry(
    total=retries_count,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)

adapter = HTTPAdapter(
    #pool_connections=concurrency + 5, 
    pool_maxsize=16,
    max_retries=retries
)
_session.mount("https://", adapter)
_session.mount("http://", adapter)
_session.headers.update(HEADERS)

# 从配置读取超时时间
TIMEOUT = config["network"]["timeout"]


def fetch_get(url: str, params=None, stream=False) -> requests.Response:
    try:
        response = _session.get(url, params=params, timeout=TIMEOUT, stream=stream)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        raise Exception(f"网络请求失败: {e}")

