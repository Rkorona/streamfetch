import xml.etree.ElementTree as ET
import json
import logging
import re
from typing import List, Dict, Optional
from streamfetch.utils.xml import decode_xml_entities

logger = logging.getLogger("streamfetch")


class DashParser:
    @staticmethod
    def _strip_ns(tag: str) -> str:
        """去除 XML 标签中的命名空间 {url}Tag -> Tag"""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    @staticmethod
    def parse(manifest_text: str) -> Optional[Dict]:
        if not manifest_text:
            return None

        trimmed = manifest_text.strip()

        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                data = json.loads(trimmed)
                if (
                    "urls" in data
                    and isinstance(data["urls"], list)
                    and len(data["urls"]) > 0
                ):
                    return {"type": "direct", "url": data["urls"][0]}
                if "url" in data and data["url"]:
                    return {"type": "direct", "url": data["url"]}
            except json.JSONDecodeError:
                pass

        try:
            clean_text = decode_xml_entities(trimmed)
            try:
                root = ET.fromstring(clean_text)
            except ET.ParseError:
                return None
            base_url = ""
            for elem in root.iter():
                if DashParser._strip_ns(elem.tag) == "BaseURL":
                    base_url = elem.text.strip() if elem.text else ""
                    break

            template = None
            for elem in root.iter():
                if DashParser._strip_ns(elem.tag) == "SegmentTemplate":
                    template = elem
                    break

            if template is None:
                if base_url:
                    return {"type": "direct", "url": base_url}
                return None

            init_url = template.get("initialization")
            media_url = template.get("media")
            start_number = int(template.get("startNumber", 1))

            if not init_url or not media_url:
                return None

            timeline_data = []
            segment_timeline = None
            for child in template:
                if DashParser._strip_ns(child.tag) == "SegmentTimeline":
                    segment_timeline = child
                    break

            if segment_timeline is not None:
                for s in segment_timeline:
                    if DashParser._strip_ns(s.tag) == "S":
                        d = int(s.get("d", 0))
                        r = int(s.get("r", 0))
                        timeline_data.append({"duration": d, "repeat": r})

            return {
                "type": "dash",
                "baseUrl": base_url,
                "template": {
                    "initializationUrl": init_url,
                    "mediaUrlTemplate": media_url,
                    "startNumber": start_number,
                    "timeline": timeline_data,
                },
            }

        except Exception as e:
            logger.debug(f"Manifest 解析失败: {e}")
            return None

    @staticmethod
    def build_urls(parsed_dash: Dict) -> List[str]:
        if parsed_dash["type"] == "direct":
            return [parsed_dash["url"]]

        base_url = parsed_dash["baseUrl"]
        t = parsed_dash["template"]

        def resolve(p: str) -> str:
            if p.startswith("http"):
                return p
            if base_url and not base_url.endswith("/") and not p.startswith("/"):
                return f"{base_url}/{p}"
            return base_url + p

        urls = [resolve(t["initializationUrl"])]
        curr = t["startNumber"]
        timeline = t["timeline"] or [{"duration": 0, "repeat": 0}]

        for entry in timeline:
            for _ in range(1 + entry["repeat"]):
                urls.append(
                    resolve(t["mediaUrlTemplate"].replace("$Number$", str(curr)))
                )
                curr += 1
        return urls

