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
        if '}' in tag:
            return tag.split('}', 1)[1]
        return tag

    @staticmethod
    def parse(manifest_text: str) -> Optional[Dict]:
        if not manifest_text:
            return None

        trimmed = manifest_text.strip()
        
        # --- 尝试 1: 解析 JSON Manifest (常见于 LOSSLESS/HIGH 音质) ---
        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                data = json.loads(trimmed)
                # JSON 格式通常包含 urls 数组
                if "urls" in data and isinstance(data["urls"], list) and len(data["urls"]) > 0:
                    return {"type": "direct", "url": data["urls"][0]}
                # 或者单 url 字段
                if "url" in data and data["url"]:
                    return {"type": "direct", "url": data["url"]}
            except json.JSONDecodeError:
                pass # 不是 JSON，继续尝试 XML

        # --- 尝试 2: 解析 XML Manifest (常见于 HI_RES / DASH) ---
        try:
            clean_text = decode_xml_entities(trimmed)
            # 忽略 XML 命名空间解析错误
            try:
                root = ET.fromstring(clean_text)
            except ET.ParseError:
                return None

            # 1. 查找 BaseURL
            base_url = ""
            for elem in root.iter():
                if DashParser._strip_ns(elem.tag) == "BaseURL":
                    base_url = elem.text.strip() if elem.text else ""
                    break
            
            # 2. 查找 SegmentTemplate (DASH 分段流)
            template = None
            for elem in root.iter():
                if DashParser._strip_ns(elem.tag) == "SegmentTemplate":
                    template = elem
                    break
            
            # --- 情况 A: 只有 BaseURL，没有分段模板 (直链) ---
            if template is None:
                if base_url:
                    # 只要有 BaseURL，就认为是直链 (不再强制检查 .flac/.mp4 后缀，因为链接可能带签名参数)
                    return {"type": "direct", "url": base_url}
                return None

            # --- 情况 B: 标准 DASH 分段流 ---
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
        # 如果是直链，直接返回列表
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