import re
from pathlib import Path

def sanitize_filename(value: str) -> str:
    """清洗单个字段，移除路径非法字符"""
    if not value:
        return "Unknown"
    # 移除 Windows/Linux 文件名保留字符 (注意：不移除斜杠 /，因为斜杠用于创建子目录)
    # 这里我们只清洗文件名组成部分，比如歌名里的 : ? * 等
    value = re.sub(r'[\\:*?"<>|]', "_", str(value))
    value = re.sub(r"\s+", " ", value)
    return value.strip()

def format_file_path(template: str, metadata: dict, base_dir: Path, extension: str = ".flac") -> Path:
    """
    根据模版生成最终文件路径
    template: 用户配置的字符串，如 "{Artist}/{Title}"
    metadata: 包含 Title, Artist 等信息的字典
    base_dir: 下载根目录
    """
    # 1. 准备替换字典 (对每个字段值进行清洗)
    safe_meta = {
        "Title": sanitize_filename(metadata.get("title", "")),
        "Artist": sanitize_filename(metadata.get("artist", "")),
        "Album": sanitize_filename(metadata.get("album", "")),
        "Year": sanitize_filename(metadata.get("year", "")),
        "Quality": sanitize_filename(metadata.get("audioQuality", "")),
        "Explicit": sanitize_filename(metadata.get("explicit", "")),
        # TrackNumber 特殊处理：补零
        "TrackNumber": str(metadata.get("trackNumber", 1)).zfill(2)
    }

    # 2. 替换模版变量
    try:
        relative_path_str = template.format(**safe_meta)
    except KeyError as e:
        # 如果用户写了不存在的变量，回退到默认
        print(f"模版变量错误: {e}，使用默认格式")
        relative_path_str = f"{safe_meta['TrackNumber']}. {safe_meta['Title']} - {safe_meta['Artist']}"

    # 3. 处理路径分隔符 (允许用户在模版里用 / 创建子文件夹)
    # 将字符串转换为 Path 对象，这会自动处理不同系统的分隔符
    final_path = base_dir / f"{relative_path_str}{extension}"
    
    # 4. 确保父目录存在
    final_path.parent.mkdir(parents=True, exist_ok=True)
    
    return final_path