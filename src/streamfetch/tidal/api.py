import base64
import urllib.parse
import logging
from streamfetch.utils.http import fetch_get

logger = logging.getLogger("streamfetch")


class TidalApi:
    def __init__(self, base_url):
        self.base_url = base_url

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
        """将毫秒转换为标准的 [mm:ss.xx] 格式"""
        try:
            t = int(ms) / 1000
            m = int(t // 60)
            s = t % 60
            return f"[{m:02d}:{s:05.2f}]"
        except:
            return ""

    def _extract_actual_lyrics(self, obj):
        """
        全量递归查找字符串，并支持动态列表转换
        """
        if not obj:
            return None

        # 1. 如果当前是字符串，判断它是否长得像歌词
        if isinstance(obj, str):
            if "\n" in obj and len(obj) > 20:
                has_timestamp = "[" in obj and ":" in obj
                return obj.strip(), has_timestamp
            return None

        # 2. 如果当前是字典，进行深度搜索
        if isinstance(obj, dict):
            # A. 优先检查当前层是否有明确的歌词键，且值是字符串
            for key in ["subtitles", "lyrics"]:
                val = obj.get(key)
                if isinstance(val, str) and len(val) > 20:
                    has_timestamp = "[" in val and ":" in val
                    return val.strip(), has_timestamp

            # B. 检查当前层是否有动态列表格式 (Python 增强逻辑，用于支持滚动)
            lines = obj.get("subtitles") or obj.get("lines")
            if isinstance(lines, list) and len(lines) > 0:
                # 检查列表项是否包含时间戳信息
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

            # C. 全量递归查找：遍历字典所有键
            for key, value in obj.items():
                # 跳过已处理的键和非目标数据类型以提高效率
                if key in ["trackId", "lyricsProvider", "album", "artist"]:
                    continue
                res = self._extract_actual_lyrics(value)
                if res:
                    return res

        # 3. 如果当前是列表，遍历每一项进行查找
        if isinstance(obj, list):
            for item in obj:
                res = self._extract_actual_lyrics(item)
                if res:
                    return res

        return None

    def search_tracks(self, query):
        logger.info(
            f'🔍 正在搜索: [bold yellow]"{query}"[/bold yellow]...',
            extra={"markup": True},
        )
        url = f"{self.base_url}/search/?s={
            urllib.parse.quote(query)
        }&limit=25&countryCode=WW"
        try:
            data = fetch_get(url).json()
            raw_items = self._find_items_array(data)
            if not raw_items:
                return []

            results = []
            for item in raw_items:
                t = item.get("item", item)
                if not t or not t.get("title"):
                    continue

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
                        "title": t.get("title"),
                        "artist": t.get("artist", {}).get("name")
                        or t.get("artists", [{}])[0].get("name")
                        or "Unknown",
                        "album": t.get("album", {}).get("title", "Unknown Album"),
                        "quality": display_quality,
                    }
                )
            return results
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []

    def get_metadata(self, track_id):
        logger.info(
            f"📡 [cyan][1/6][/cyan] 获取元数据 (ID: {track_id})...",
            extra={"markup": True},
        )
        resp = fetch_get(f"{self.base_url}/info/?id={track_id}").json()
        info = resp.get("data", resp)

        # 1. 获取基础音质
        base_quality = info.get("audioQuality", "LOSSLESS")

        # 2. 获取高级标签
        media_metadata = info.get("mediaMetadata", {})
        tags = media_metadata.get("tags", [])

        # 3. 判定有效最高音质
        # 如果标签里明确写了 HIRES_LOSSLESS，强制提升为 HI_RES
        if "HIRES_LOSSLESS" in tags:
            effective_quality = "HI_RES"
        # 兼容旧版 MQA 标签
        elif "MQA" in tags:
            effective_quality = "HI_RES"
        # 否则使用基础音质
        else:
            effective_quality = base_quality

        date_str = info.get("streamStartDate") or info.get("releaseDate")
        year = date_str.split("-")[0] if date_str else "Unknown"

        # 3. 获取脏标 (Explicit)
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

    def get_lyrics(self, track_id):
        logger.info(f"📝 [cyan][2/6][/cyan] 获取歌词...", extra={"markup": True})
        try:
            resp = fetch_get(f"{self.base_url}/lyrics/?id={track_id}")
            data = resp.json()

            result = self._extract_actual_lyrics(data)
            if result:
                text, is_sync = result
                type_str = "滚动歌词" if is_sync else "纯文本"
                logger.info(
                    f"   -> 提取成功 ([bold green]{type_str}[/bold green])",
                    extra={"markup": True},
                )
                return {"text": text, "isLrc": is_sync}

            logger.warning("   -> 未能在 API 返回中找到有效歌词内容")
        except Exception as e:
            logger.debug(f"歌词提取失败详情: {e}")
        return None

    def get_stream_manifest(self, track_id, quality):
        q_name = "Hi-Res" if quality == "HI_RES_LOSSLESS" else "Lossless"
        logger.info(
            f"🌐 [cyan][3/6][/cyan] 获取流清单 ({q_name})...", extra={"markup": True}
        )
        data = fetch_get(
            f"{self.base_url}/track/?id={track_id}&quality={quality}"
        ).json()
        container = data.get("data", data)
        manifest_b64 = container.get("manifest") or container.get("info", {}).get(
            "manifest"
        )
        if not manifest_b64:
            raise Exception("API 未返回 Manifest")
        return base64.b64decode(manifest_b64).decode("utf-8")

    def get_album(self, album_id):
        data = fetch_get(f"{self.base_url}/album/?id={album_id}").json()
        if "data" in data:
            items = data["data"].get("items", [])
            album_info = (
                items[0].get("item", items[0]).get("album", {}) if items else {}
            )
        else:
            album_info = data[0] if isinstance(data, list) else {}
            items = (
                data[1].get("items", [])
                if isinstance(data, list) and len(data) > 1
                else []
            )
        return {
            "albumInfo": album_info,
            "tracks": [i.get("item", i) for i in items if i.get("item", i).get("id")],
        }

    def get_playlist(self, playlist_uuid):
        """
        获取歌单详情及所有歌
        """
        logger.info(f"📋 正在获取歌单信息: {playlist_uuid}...", extra={"markup": True})

        # 基础 URL
        base_api_url = f"{self.base_url}/playlist/"

        # 初始参数
        params = {"id": playlist_uuid, "offset": 0, "limit": 100, "countryCode": "WW"}

        try:
            resp = fetch_get(base_api_url, params=params).json()
        except Exception as e:
            raise Exception(f"无法获取歌单信息: {e}")

        # 2. 解析元数据 (修复点：优先查找 'playlist' 字段)
        info = resp.get("playlist") or resp.get("data") or resp.get("info") or resp

        # 3. 循环获取所有歌曲
        all_tracks = []

        logger.info("   -> 正在加载歌曲列表...", extra={"markup": True})

        while True:
            # 查找 items 数组
            current_items = self._find_items_array(resp)

            if not current_items:
                break

            # 提取有效歌曲
            for item in current_items:
                if isinstance(item, dict) and item.get("type") == "video":
                    continue

                # 2. 提取内层数据
                track = item.get("item", item)

                # 3. 验证有效性
                if track and track.get("id") and track.get("title"):
                    if track.get("type") == "VIDEO":
                        continue

                    all_tracks.append(track)

            if len(current_items) < params["limit"]:
                break

            params["offset"] += params["limit"]

            try:
                resp = fetch_get(base_api_url, params=params).json()
            except Exception as e:
                logger.warning(f"分页加载中断: {e}")
                break

        return {"info": info, "tracks": all_tracks}

