import typer
import re
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from streamfetch.config.api_targets import get_base_url
from streamfetch.tidal.api import TidalApi
from streamfetch.tidal.downloader import TidalDownloader
from streamfetch.cli.interactive import interactive_search
from streamfetch.config.settings import config
from streamfetch.utils.logging_config import logger

console = Console()
app = typer.Typer(
    help="StreamFetch - 一个音乐下载工具",
    add_completion=False,
    rich_markup_mode="rich",
)

def get_context():
    """初始化 API、下载器及基础目录"""
    base_url = get_base_url()
    api = TidalApi(base_url)
    downloader = TidalDownloader(api)

    download_dir = Path(config["general"]["download_dir"])
    if not download_dir.is_absolute():
        download_dir = Path.cwd() / download_dir
    download_dir.mkdir(parents=True, exist_ok=True)

    return api, downloader, download_dir

def extract_id(input_str: str) -> str:
    """提取链接或字符串中的 ID (UUID 或 数字)"""
    uuid_pattern = r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    match = re.search(uuid_pattern, input_str)
    if match: return match.group(1)
    
    id_pattern = r"(\d+)"
    match = re.search(id_pattern, input_str)
    if match: return match.group(1)
    
    return input_str.strip()

@app.command()
def search(query: str = typer.Argument(..., help="搜索关键词")):
    """🔍 交互式搜索并下载歌曲"""
    api, downloader, download_dir = get_context()
    interactive_search(api, downloader, query, download_dir)

@app.command()
def track(link_or_id: str = typer.Argument(..., help="歌曲链接 或 ID")):
    """🎵 下载单首歌曲"""
    api, downloader, download_dir = get_context()
    downloader.process_track(extract_id(link_or_id), download_dir)

@app.command()
def album(link_or_id: str = typer.Argument(..., help="专辑链接 或 ID")):
    """💿 下载整张专辑"""
    api, downloader, download_dir = get_context()
    downloader.download_album(extract_id(link_or_id), download_dir)

@app.command()
def playlist(link_or_id: str = typer.Argument(..., help="歌单链接 或 UUID")):
    """📜 下载歌单"""
    api, downloader, download_dir = get_context()
    playlist_id = extract_id(link_or_id)

    try:
        data = api.get_playlist(playlist_id)
        info, tracks = data["info"], data["tracks"]

        if not tracks:
            console.print("[bold red]❌ 歌单为空[/bold red]")
            return

        # 展示歌单预览
        table = Table(title="🎵 歌单确认", show_header=False, box=None)
        table.add_row("[bold cyan]标题:[/bold cyan]", info.get("title", "Unknown"))
        table.add_row("[bold cyan]歌曲数:[/bold cyan]", f"[green]{len(tracks)}[/green]")
        console.print(Panel(table, expand=False, border_style="cyan"))

        if typer.confirm("❓ 确认下载吗?"):
            downloader.download_playlist(tracks, download_dir)
            
    except Exception as e:
        logger.error(f"处理歌单失败: {e}")

if __name__ == "__main__":
    app()