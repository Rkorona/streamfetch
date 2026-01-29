from rich.table import Table
from rich.console import Console

console = Console()


def interactive_search(api, downloader, query, download_dir):
    results = api.search_tracks(query)
    if not results:
        console.print("[red]未找到相关歌曲。[/red]")
        return

    table = Table(
        title=f"搜索结果: {query}", show_header=True, header_style="bold magenta"
    )
    table.add_column("序号", style="dim", width=6)
    table.add_column("标题", style="white")
    table.add_column("歌手", style="green")
    table.add_column("质量", style="cyan")

    for idx, item in enumerate(results):
        table.add_row(str(idx + 1), item["title"], item["artist"], item["quality"])

    console.print(table)
    choice = input(f"\n📥 请输入序号 (1-{len(results)})，0 退出: ")
    if choice.isdigit() and 0 < int(choice) <= len(results):
        selected = results[int(choice) - 1]
        downloader.process_track(selected["id"], download_dir)
