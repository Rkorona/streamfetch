import typer
import re
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from streamfetch.utils.logging_config import logger
from streamfetch.config.api_targets import get_base_url
from streamfetch.tidal.api import TidalApi
from streamfetch.tidal.downloader import TidalDownloader
from streamfetch.cli.interactive import interactive_search
from streamfetch.config.settings import config

console = Console()
app = typer.Typer(
    help="StreamFetch - 一个 FLAC 音乐下载工具",
    add_completion=False,
    rich_markup_mode="rich",
)


def get_context():
    """初始化 API 和 下载器"""
    base_url = get_base_url()
    api = TidalApi(base_url)
    downloader = TidalDownloader(api)

    # 从配置读取下载目录
    download_path_str = config["general"]["download_dir"]
    download_dir = Path(download_path_str)

    if not download_dir.is_absolute():
        download_dir = Path.cwd() / download_dir

    download_dir.mkdir(parents=True, exist_ok=True)

    return api, downloader, download_dir


def extract_uuid(input_str: str) -> str:
    """从 URL 或字符串中提取 UUID"""
    uuid_pattern = (
        r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    )
    id_pattern = r"(\d+)"

    match = re.search(uuid_pattern, input_str)
    if match:
        return match.group(1)

    match = re.search(id_pattern, input_str)
    if match:
        return match.group(1)

    return input_str.strip()


@app.command()
def search(query: str = typer.Argument(..., help="搜索关键词")):
    """
    🔍 交互式搜索并下载歌曲
    """
    api, downloader, download_dir = get_context()
    interactive_search(api, downloader, query, download_dir)


@app.command()
def playlist(link_or_id: str = typer.Argument(..., help="歌单链接 或 UUID")):
    """
    📜 下载歌单
    """
    api, downloader, download_dir = get_context()

    playlist_uuid = extract_uuid(link_or_id)
    if not playlist_uuid:
        console.print("[bold red]❌ 无法从输入中提取有效的歌单 ID[/bold red]")
        raise typer.Exit(code=1)

    try:
        data = api.get_playlist(playlist_uuid)
        info = data["info"]
        tracks = data["tracks"]

        if not tracks:
            console.print("[bold red]❌ 歌单为空或无法解析歌曲列表[/bold red]")
            raise typer.Exit(code=1)

        title = info.get("title", "Unknown Playlist")
        creator = info.get("creator", {}).get("name", "Unknown User")
        desc = info.get("description", "")

        console.print("\n")
        table = Table(title="🎵 歌单确认", show_header=False, box=None)
        table.add_row(
            "[bold cyan]标题:[/bold cyan]", f"[bold white]{title}[/bold white]"
        )
        table.add_row("[bold cyan]创建者:[/bold cyan]", creator)
        table.add_row(
            "[bold cyan]歌曲数:[/bold cyan]", f"[green]{len(tracks)}[/green] 首"
        )
        if desc:
            table.add_row("[bold cyan]描述:[/bold cyan]", f"[dim]{desc[:50]}...[/dim]")

        console.print(Panel(table, expand=False, border_style="cyan"))

        if not typer.confirm("❓ 确认下载此歌单吗?"):
            console.print("[yellow]已取消操作[/yellow]")
            raise typer.Exit()

        # --- 修改点：不再创建子文件夹，直接使用根下载目录 ---
        # 目录结构完全由 config.yaml 中的 file_format 控制
        logger.info(
            f"📂 基础下载目录: [bold]{download_dir}[/bold]", extra={"markup": True}
        )

        for i, track in enumerate(tracks):
            track_name = track.get("title", "Unknown")
            track_id = track.get("id")
            console.print(
                f"\n[bold]Processing {i+1}/{len(tracks)}:[/bold] {track_name}"
            )

            try:
                downloader.process_track(track_id, download_dir)
            except Exception as e:
                logger.error(f"歌曲 {track_name} 下载失败: {e}")

    except Exception as e:
        logger.error(f"❌ 处理歌单时出错: {e}")
        import traceback

        logger.debug(traceback.format_exc())


@app.command()
def album(link_or_id: str = typer.Argument(..., help="专辑链接 或 ID")):
    """
    💿 下载整张专辑
    """
    api, downloader, download_dir = get_context()
    album_id = extract_uuid(link_or_id)

    try:
        data = api.get_album(album_id)

        # 修复 Unknown Artist 问题：尝试从 artists 列表获取
        album_info = data["albumInfo"]
        album_name = album_info.get("title", "Unknown Album")
        artist_name = (
            album_info.get("artist", {}).get("name")
            or album_info.get("artists", [{}])[0].get("name")
            or "Unknown Artist"
        )

        logger.info(
            f"💿 识别专辑: [bold]{album_name}[/bold] - {artist_name}",
            extra={"markup": True},
        )

        # --- 修改点：不再创建子文件夹，直接使用根下载目录 ---
        # 之前的代码在这里创建了 safe_folder_name 并赋值给了 album_dir
        # 现在直接把 download_dir 传给 downloader，让 config.yaml 决定路径

        tracks = data.get("tracks", [])
        logger.info(f"📊 发现 {len(tracks)} 首歌曲")

        for track in tracks:
            downloader.process_track(track["id"], download_dir)

    except Exception as e:
        logger.error(f"专辑下载失败: {e}")


if __name__ == "__main__":
    app()
