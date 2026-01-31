import requests
import re
import logging
from urllib.parse import quote

logger = logging.getLogger("streamfetch")


class LRCLib:
    BASE_URL = "https://lrclib.net/api"
    HEADERS = {
        "User-Agent": "StreamFetch/1.0 (https://github.com/yourname/streamfetch)"
    }

    @staticmethod
    def _simplify_track_name(name: str) -> str:
        patterns = [
            r"\s*\(feat\..*?\)",
            r"\s*\(ft\..*?\)",
            r"\s*\(featuring.*?\)",
            r"\s*\(with.*?\)",
            r"\s*-\s*Remaster(ed)?.*$",
            r"\s*-\s*\d{4}\s*Remaster.*$",
            r"\s*\(Remaster(ed)?.*?\)",
            r"\s*\(Deluxe.*?\)",
            r"\s*\(Bonus.*?\)",
            r"\s*\(Live.*?\)",
            r"\s*\(Acoustic.*?\)",
            r"\s*\(Radio Edit\)",
            r"\s*\(Single Version\)",
        ]
        result = name
        for p in patterns:
            result = re.sub(p, "", result, flags=re.IGNORECASE)
        return result.strip()

    @staticmethod
    def _fetch_get(artist: str, track: str):
       
        try:
            params = {"artist_name": artist, "track_name": track}
            resp = requests.get(
                f"{LRCLib.BASE_URL}/get",
                params=params,
                headers=LRCLib.HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    @staticmethod
    def _fetch_search(query: str, duration_sec: float):
        
        try:
            params = {"q": query}
            resp = requests.get(
                f"{LRCLib.BASE_URL}/search",
                params=params,
                headers=LRCLib.HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for item in data:
                        item_dur = item.get("duration", 0)
                        if abs(item_dur - duration_sec) <= 10:
                          
                            if item.get("syncedLyrics"):
                                return item
                         
                            if item.get("plainLyrics"):
                                return item
        except Exception:
            pass
        return None

    @staticmethod
    def get_lyrics(track_name: str, artist_name: str, duration_sec: float):

        res = LRCLib._fetch_get(artist_name, track_name)
        if res and (res.get("syncedLyrics") or res.get("plainLyrics")):
            return {
                "text": res.get("syncedLyrics") or res.get("plainLyrics"),
                "isLrc": bool(res.get("syncedLyrics")),
            }

        simple_track = LRCLib._simplify_track_name(track_name)
        if simple_track != track_name:
            res = LRCLib._fetch_get(artist_name, simple_track)
            if res and (res.get("syncedLyrics") or res.get("plainLyrics")):
                return {
                    "text": res.get("syncedLyrics") or res.get("plainLyrics"),
                    "isLrc": bool(res.get("syncedLyrics")),
                }

        query = f"{artist_name} {track_name}"
        res = LRCLib._fetch_search(query, duration_sec)
        if res:
            return {
                "text": res.get("syncedLyrics") or res.get("plainLyrics"),
                "isLrc": bool(res.get("syncedLyrics")),
            }

        if simple_track != track_name:
            query = f"{artist_name} {simple_track}"
            res = LRCLib._fetch_search(query, duration_sec)
            if res:
                return {
                    "text": res.get("syncedLyrics") or res.get("plainLyrics"),
                    "isLrc": bool(res.get("syncedLyrics")),
                }

        logger.debug("❌ LRCLib 也未找到歌词")
        return None
