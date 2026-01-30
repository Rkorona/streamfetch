import base64
import urllib.parse
import logging
import time
from streamfetch.utils.http import fetch_get
from streamfetch.config.api_targets import get_base_url

logger = logging.getLogger("streamfetch")


class TidalApi:
    def __init__(self, base_url):
        self.base_url = base_url

    def _switch_server(self):
        """辅助函数：切换到新的服务器"""
        old_url = self.base_url
        for _ in range(3):
            new_url = get_base_url()
            if new_url != old_url:
                self.base_url = new_url
                break

        logger.warning(
            f"⚠️  服务器异常 [dim]({old_url})[/dim]，切换至: [cyan]{
                self.base_url
            }[/cyan]",
            extra={"markup": True},
        )

    def _find_items_array(self, obj):
        if not obj or not isinstance(obj, (dict, list)):
            return None
        if isinstance(obj, list) and len(obj) > 0:
            t = obj[0].get("item", obj[0])
            if isinstance(t, dict) and "id" in t:
                return obj
        if isinstance(obj, dict):
            for key in ["items", "tracks", "data"]:
                found = self._find_items_array(obj.get(key))
                if found:
                    return found
            for key, val in obj.items():
                if key in ["albums", "artists", "playlists"]:
                    continue
                found = self._find_items_array(val)
                if found:
                    return found
        return None

    def _ms_to_lrc(self, ms):
        try:
            t = int(ms) / 1000
            m = int(t // 60)
            s = t % 60
            return f"[{m:02d}:{s:05.2f}]"
        except:
            return ""

    def _extract_actual_lyrics(self, obj):
        if not obj:
            return None
        if isinstance(obj, str):
            if "\n" in obj and len(obj) > 20:
                has_timestamp = "[" in obj and ":" in obj
                return obj.strip(), has_timestamp
            return None
        if isinstance(obj, dict):
            for key in ["subtitles", "lyrics"]:
                val = obj.get(key)
                if isinstance(val, str) and len(val) > 20:
                    has_timestamp = "[" in val and ":" in val
                    return val.strip(), has_timestamp
            lines = obj.get("subtitles") or obj.get("lines")
            if isinstance(lines, list) and len(lines) > 0:
                first = lines[0]
                if isinstance(first, dict) and (
                    "startTime" in first or "start" in first
                ):
                    lrc_lines = []
                    for item in lines:
                        start = item.get("startTime") or item.get("start")
                        word = item.get("words") or item.get("text") or ""
                        if start is not None:
                            timestamp = self._ms_to_lrc(start)
                            lrc_lines.append(f"{timestamp}{word}")
                    if lrc_lines:
                        return "\n".join(lrc_lines), True
            for key, value in obj.items():
                if key in ["trackId", "lyricsProvider", "album", "artist"]:
                    continue
                res = self._extract_actual_lyrics(value)
                if res:
                    return res
        if isinstance(obj, list):
            for item in obj:
                res = self._extract_actual_lyrics(item)
                if res:
                    return res
        return None

    def search_tracks(self, query):
        logger.info(
            f'🔍 Searching: [bold yellow]"{query}"[/bold yellow]...',
            extra={"markup": True},
        )

        max_retries = 6

        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}/search/?s={
                    urllib.parse.quote(query)
                }&limit=25&countryCode=WW"
                resp = fetch_get(url)
                data = resp.json()

                raw_items = self._find_items_array(data)

                if not raw_items:
                    return []

                results = []
                for item in raw_items:
                    t = item.get("item", item)
                    if not t or not t.get("title"):
                        continue

                    # --- 修改点 1: 处理 Version 字段 ---
                    title = t.get("title")
                    version = t.get("version")
                    if version:
                        title = f"{title} ({version})"

                    base_quality = t.get("audioQuality", "Unknown")
                    tags = t.get("mediaMetadata", {}).get("tags", [])

                    if "HIRES_LOSSLESS" in tags:
                        display_quality = "HI_RES"
                    elif "MQA" in tags:
                        display_quality = "HI_RES"
                    else:
                        display_quality = base_quality

                    results.append(
                        {
                            "id": str(t.get("id")),
                            "title": title,  # 使用带版本号的标题
                            "artist": t.get("artist", {}).get("name")
                            or t.get("artists", [{}])[0].get("name")
                            or "Unknown",
                            "album": t.get("album", {}).get("title", "Unknown Album"),
                            "quality": display_quality,
                        }
                    )
                return results

            except Exception as e:
                is_last_attempt = attempt == max_retries - 1

                if is_last_attempt:
                    logger.error(f"❌ 搜索最终失败: {e}")
                    return []

                self._switch_server()
                time.sleep(0.5)

        return []

    def get_metadata(self, track_id):
        logger.debug(f"📡 [1/6] Getting metadata (ID: {track_id})...")

        max_retries = 6
        for attempt in range(max_retries):
            try:
                resp = fetch_get(f"{self.base_url}/info/?id={track_id}").json()
                info = resp.get("data", resp)

                if not info or "title" not in info:
                    raise Exception("Invalid metadata response")

                base_quality = info.get("audioQuality", "LOSSLESS")
                media_metadata = info.get("mediaMetadata", {})
                tags = media_metadata.get("tags", [])

                if "HIRES_LOSSLESS" in tags:
                    effective_quality = "HI_RES"
                elif "MQA" in tags:
                    effective_quality = "HI_RES"
                else:
                    effective_quality = base_quality

                date_str = info.get("streamStartDate") or info.get("releaseDate")
                year = date_str.split("-")[0] if date_str else "Unknown"
                is_explicit = info.get("explicit", False)
                explicit_tag = "E" if is_explicit else ""

                return {
                    "title": info.get("title", "Unknown Title"),
                    "album": info.get("album", {}).get("title", "Unknown Album"),
                    "artist": info.get("artist", {}).get("name")
                    or info.get("artists", [{}])[0].get("name")
                    or "Unknown Artist",
                    "trackNumber": info.get("trackNumber", 1),
                    "coverId": info.get("album", {}).get("cover") or info.get("cover"),
                    "audioQuality": effective_quality,
                    "year": year,
                    "explicit": explicit_tag,
                }
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                self._switch_server()
                time.sleep(0.5)

    def get_lyrics(self, track_id):
        logger.debug(f"📝 [2/6] Getting lyrics...")
        try:
            resp = fetch_get(f"{self.base_url}/lyrics/?id={track_id}")
            data = resp.json()
            result = self._extract_actual_lyrics(data)
            if result:
                text, is_sync = result
                return {"text": text, "isLrc": is_sync}
        except Exception:
            pass
        return None

    def get_stream_manifest(self, track_id, quality):
        logger.debug(f"🌐 [3/6] Getting manifest ({quality})...")

        max_retries = 6
        for attempt in range(max_retries):
            try:
                data = fetch_get(
                    f"{self.base_url}/track/?id={track_id}&quality={quality}"
                ).json()
                container = data.get("data", data)
                manifest_b64 = container.get("manifest") or container.get(
                    "info", {}
                ).get("manifest")
                if not manifest_b64:
                    raise Exception("API returned no manifest")

                return base64.b64decode(manifest_b64).decode("utf-8")

            except Exception as e:
                if "404" in str(e) and attempt >= 2:
                    raise e

                if attempt == max_retries - 1:
                    raise e

                self._switch_server()
                time.sleep(0.5)

    def get_album(self, album_id):
        max_retries = 6
        for attempt in range(max_retries):
            try:
                # 1. 请求专辑详情
                resp = fetch_get(f"{self.base_url}/album/?id={album_id}").json()
                
                # 2. 提取专辑元数据 (Root Data)
                # 这里的 data 包含了 title, artist(关键!), 以及 items (歌曲列表)
                album_info = resp.get("data", resp)

                # 3. 提取歌曲列表
                # 优先从当前响应里找 (根据你提供的 JSON，items 就在 data 里)
                # _find_items_array 会递归查找 items 数组
                raw_items = self._find_items_array(album_info)

                # 4. 如果当前响应里没歌 (针对部分不返回 items 的镜像站)，才去请求 items 接口
                if not raw_items:
                    # logger.debug("专辑详情未包含歌曲，尝试请求 items 接口...")
                    tracks_url = f"{self.base_url}/album/items/?id={album_id}&limit=100&offset=0"
                    try:
                        tracks_resp = fetch_get(tracks_url).json()
                        raw_items = self._find_items_array(tracks_resp)
                    except:
                        pass
                
                if not raw_items:
                    raw_items = []

                # 5. 格式化歌曲
                clean_tracks = []
                for item in raw_items:
                    t = item.get("item", item)
                    if t and t.get("id"):
                        # 顺便把之前做的 Version 优化也加上
                        title = t.get("title")
                        version = t.get("version")
                        if version:
                            t["title"] = f"{title} ({version})"
                        clean_tracks.append(t)

                return {
                    "albumInfo": album_info, # 这里现在是包含 artist 的完整对象了
                    "tracks": clean_tracks
                }

            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                self._switch_server()
                time.sleep(0.5)

    def get_playlist(self, playlist_uuid):
        logger.info(f"📋 Fetching playlist: {playlist_uuid}...", extra={"markup": True})

        max_retries = 6
        resp = None
        base_api_url = None
        params = {"id": playlist_uuid, "offset": 0, "limit": 100, "countryCode": "WW"}

        for attempt in range(max_retries):
            try:
                base_api_url = f"{self.base_url}/playlist/"
                resp = fetch_get(base_api_url, params=params).json()
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise Exception(f"无法获取歌单信息: {e}")
                self._switch_server()
                time.sleep(0.5)

        info = resp.get("playlist") or resp.get("data") or resp.get("info") or resp
        all_tracks = []

        logger.info("   -> Loading tracks...", extra={"markup": True})

        while True:
            current_items = self._find_items_array(resp)
            if not current_items:
                break
            for item in current_items:
                if isinstance(item, dict) and item.get("type") == "video":
                    continue
                track = item.get("item", item)
                if track and track.get("id") and track.get("title"):
                    if track.get("type") == "VIDEO":
                        continue
                    all_tracks.append(track)
            if len(current_items) < params["limit"]:
                break
            params["offset"] += params["limit"]
            try:
                resp = fetch_get(base_api_url, params=params).json()
            except Exception:
                break
        return {"info": info, "tracks": all_tracks}
