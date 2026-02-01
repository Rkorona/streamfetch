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
        old_url = self.base_url
        for _ in range(3):
            new_url = get_base_url()
            if new_url != old_url:
                self.base_url = new_url
                break

        logger.warning(
            f"⚠️ 服务器异常，切换至下一个服务器",
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
        # --- 1. 输入预处理 ---
        search_query = query
        match_parts = []

        if " - " in query:
            temp_parts = query.split(" - ", 1)
            match_parts = [p.strip().lower() for p in temp_parts if p.strip()]
            search_query = " ".join(match_parts)

            logger.info(
                f'🔍 识别到组合搜索: "[cyan]{match_parts[0]}[/cyan]" + "[cyan]{
                    match_parts[1]
                }[/cyan]"',
                extra={"markup": True},
            )
        else:
            logger.info(
                f'🔍 Searching: [bold yellow]"{query}"[/bold yellow]...',
                extra={"markup": True},
            )

        max_retries = 6

        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}/search/?s={
                    urllib.parse.quote(search_query)
                }&limit=25&countryCode=WW"

                resp = fetch_get(url)
                data = resp.json()

                raw_items = self._find_items_array(data)

                if not raw_items:
                    if attempt == 0 and match_parts:
                        logger.debug("组合搜索未命中，尝试原始关键词...")
                        search_query = query
                        continue
                    return []

                results = []
                for item in raw_items:
                    t = item.get("item", item)
                    if not t or not t.get("title"):
                        continue

                    title = t.get("title")
                    version = t.get("version")
                    if version:
                        title = f"{title} ({version})"

                    base_quality = t.get("audioQuality", "Unknown")
                    tags = t.get("mediaMetadata", {}).get("tags", [])
                    if "HIRES_LOSSLESS" in tags or "MQA" in tags:
                        display_quality = "HI_RES"
                    else:
                        display_quality = base_quality

                    artists_list = t.get("artists", [])
                    if artists_list:
                        artist_names = [
                            a.get("name") for a in artists_list if a.get("name")
                        ]
                        artist_name = ", ".join(artist_names)
                    else:
                        artist_name = t.get("artist", {}).get("name", "Unknown")

                    results.append(
                        {
                            "id": str(t.get("id")),
                            "title": title,
                            "artist": artist_name,
                            "album": t.get("album", {}).get("title", "Unknown Album"),
                            "quality": display_quality,
                        }
                    )

                if match_parts and len(match_parts) == 2 and results:
                    part_a = match_parts[0]
                    part_b = match_parts[1]

                    high_priority = []
                    normal_priority = []

                    for item in results:
                        r_title = item["title"].lower()

                        r_artist = item["artist"].lower()

                        match_1 = (part_a in r_title) and (part_b in r_artist)
                        match_2 = (part_b in r_title) and (part_a in r_artist)

                        if match_1 or match_2:
                            high_priority.append(item)
                        else:
                            normal_priority.append(item)

                    if high_priority:
                        logger.info(
                            f"✨ 精确匹配到 {len(high_priority)} 个结果，已置顶"
                        )
                        return high_priority + normal_priority

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
                    "duration": info.get("duration", 0),
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
                resp = fetch_get(f"{self.base_url}/album/?id={album_id}").json()

                album_info = resp.get("data", resp)

                raw_items = self._find_items_array(album_info)

                if not raw_items:
                    tracks_url = (
                        f"{self.base_url}/album/items/?id={album_id}&limit=100&offset=0"
                    )
                    try:
                        tracks_resp = fetch_get(tracks_url).json()
                        raw_items = self._find_items_array(tracks_resp)
                    except:
                        pass

                if not raw_items:
                    raw_items = []

    
                clean_tracks = []
                for item in raw_items:
                    t = item.get("item", item)
                    if t and t.get("id"):
                        title = t.get("title")
                        version = t.get("version")
                        if version:
                            t["title"] = f"{title} ({version})"
                        clean_tracks.append(t)

                return {"albumInfo": album_info, "tracks": clean_tracks}

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
