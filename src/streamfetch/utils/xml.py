import html


def decode_xml_entities(s: str) -> str:
    if not s:
        return s
    return html.unescape(s)
