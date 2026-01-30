import yaml
import sys
from pathlib import Path
from rich.console import Console

console = Console()

# 默认配置
DEFAULT_CONFIG = {
    "general": {"download_dir": "./downloads", "log_level": "INFO"},
    "audio": {"max_quality": "HI_RES", "auto_fallback": True},
    "network": {
        "api_urls": ["https://tidal.kinoplus.online"],
        "concurrency": 8,
        "timeout": 30,
        "max_retries": 3,
    },
    "lyrics": {"save_lrc": True},
    "ffmpeg": {"binary": "ffmpeg"},
    "naming": {"file_format": "{Title} - {Artist}"},
}


def find_config_file():
    """
    尝试在多个位置查找配置文件
    """
    # 1. 优先检查当前工作目录 (CWD)
    cwd = Path.cwd()
    candidates = [cwd / "config.yaml", cwd / "config.yml"]

    try:
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent.parent
        candidates.append(project_root / "config.yaml")
        candidates.append(project_root / "config.yml")
    except Exception:
        pass

    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def load_config():
    config_path = find_config_file()
    if not config_path:
        console.print(
            "[bold yellow]⚠️  未找到配置文件 (config.yaml 或 config.yml)，正在使用内置默认设置。[/bold yellow]",
            style="yellow",
        )
        return DEFAULT_CONFIG

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f)

            if not user_config:
                console.print(
                    f"[bold red]❌ 配置文件为空: {config_path}，使用默认设置[/bold red]"
                )
                return DEFAULT_CONFIG

            console.print(f"[dim]⚙️  已加载配置文件: {config_path}[/dim]")

            # 深度合并配置 (User Config 覆盖 Default Config)
            final_config = DEFAULT_CONFIG.copy()
            for section, values in user_config.items():
                if section in final_config and isinstance(values, dict):
                    final_config[section].update(values)
                else:
                    final_config[section] = values
            return final_config

    except Exception as e:
        console.print(
            f"[bold red]❌ 配置文件加载出错: {e}，正在使用默认设置[/bold red]"
        )
        return DEFAULT_CONFIG


config = load_config()
