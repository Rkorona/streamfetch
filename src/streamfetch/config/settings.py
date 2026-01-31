import yaml
import os
import sys
from pathlib import Path
from rich.console import Console
import typer

console = Console()

APP_NAME = "streamfetch"

DEFAULT_YAML_TEMPLATE = """
general:
  # 下载保存的根目录 (支持相对路径或绝对路径)
  # 留空则默认下载到当前运行目录下的 downloads_music 文件夹
  download_dir: "./downloads_music"
  log_level: "INFO"

audio:
  # 目标最高音质: HIRES_LOSSLESS, LOSSLESS, HIGH
  # HIRES_LOSSLESS   = Master / Hi-Res FLAC
  # LOSSLESS = HiFi / CD FLAC
  # HIGH     = High / 320kbps AAC
  max_quality: "HIRES_LOSSLESS"
  # 如果最高音质不可用，是否允许自动降级下载 (True/False)
  auto_fallback: True

network:
  # API 服务器列表
  # 程序会随机选择其中一个
  api_urls:
    - "https://tidal.kinoplus.online"
    - "https://api.tidalhifi.com"
  # DASH 分段下载并发数
  concurrency: 10
  # 请求超时时间 (秒)
  timeout: 30
  # 失败重试次数
  max_retries: 3

lyrics:
  # 是否保存为外部 .lrc 文件 (True/False)
  save_lrc: False

ffmpeg:
  # FFmpeg 可执行文件路径
  # 如果已添加到系统环境变量，直接填 "ffmpeg" 
  # 否则填绝对路径，例如: "C:/Tools/ffmpeg/bin/ffmpeg.exe"
  binary: "ffmpeg"

naming:
  file_format: "{Artist}/{Album}/{Title}"
  # 自定义文件名/目录格式
  # 支持的变量:
  # {Title}       - 歌名
  # {Artist}      - 歌手名
  # {Album}       - 专辑名
  # {TrackNumber} - 歌曲序号 (自动补零, 如 01)
  # {Year}        - 发行年份
  # {Quality}     - 音质 (Hi-Res, Lossless)
  # {Explicit}    - 脏标 (E 或 空)
"""

# 用于程序内部回退的字典默认值（防止 YAML 解析失败时程序崩溃）
INTERNAL_DEFAULTS = {
    "general": {"download_dir": "./downloads_music", "log_level": "INFO"},
    "audio": {"max_quality": "HIRES_LOSSLESS", "auto_fallback": True},
    "network": {
        "api_urls": ["https://tidal.kinoplus.online"],
        "concurrency": 16,
        "timeout": 30,
        "max_retries": 3,
    },
    "lyrics": {"save_lrc": False},
    "ffmpeg": {"binary": "ffmpeg"},
    "naming": {"file_format": "{Artist}/{Album}/{Title}"},
}

def get_config_path() -> Path:
    cwd_config = Path.cwd() / "config.yml"
    if cwd_config.exists():
        return cwd_config

    app_dir = Path(typer.get_app_dir(APP_NAME))
    config_path = app_dir / "config.yml"
    
    return config_path

def ensure_config_exists(config_path: Path):
    """
    如果配置文件不存在，则创建默认配置
    """
    if not config_path.exists():
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(DEFAULT_YAML_TEMPLATE.strip())
            
            console.print(f"[bold green]✨ 初次运行，已生成默认配置文件: {config_path}[/bold green]")
            console.print(f"[dim]根据需要修改该文件来自定义设置。[/dim]")
        except Exception as e:
            console.print(f"[bold red]❌ 无法创建配置文件: {e}[/bold red]")

def load_config():

    config_path = get_config_path()
    
    ensure_config_exists(config_path)

    final_config = INTERNAL_DEFAULTS.copy()

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f)
                
            if user_config:
                # 深度合并配置
                for section, values in user_config.items():
                    if section in final_config and isinstance(values, dict):
                        final_config[section].update(values)
                    else:
                        final_config[section] = values
            
            if config_path.parent != Path.cwd():
                 pass

        except Exception as e:
            console.print(f"[bold red]⚠️ 配置文件格式错误: {e}，将使用默认设置[/bold red]")
    
    return final_config

config = load_config()