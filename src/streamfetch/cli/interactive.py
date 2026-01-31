from rich.table import Table
from rich.console import Console

console = Console()


def interactive_search(api, downloader, query, download_dir):
    results = api.search_tracks(query)
    if not results:
        console.print("[red]未找到相关歌曲。[/red]")
        return
    table = Table(
        title=f"搜索结果: {query}",
        show_header=True,
        header_style="bold cyan",
        expand=True,  # 让表格填满终端宽度
        box=None,  # 移除竖线边框
        padding=(0, 1),  # 增加列间距
    )

    # 1. 序号：固定宽度，不换行
    table.add_column("序号", style="dim", width=4, justify="center", no_wrap=True)

    # 2. 标题：占比最大，超出显示省略号 (...)
    table.add_column("标题", style="white", ratio=2, no_wrap=True, overflow="ellipsis")

    # 3. 专辑：占比次之，超出显示省略号
    table.add_column("专辑", style="yellow", ratio=2, no_wrap=True, overflow="ellipsis")

    # 4. 歌手：超出显示省略号
    table.add_column("歌手", style="green", ratio=1, no_wrap=True, overflow="ellipsis")

    # 5. 质量：固定宽度，右对齐 
    table.add_column("质量", style="cyan", width=8, justify="left", no_wrap=True)

    for idx, item in enumerate(results):
        table.add_row(
            str(idx + 1), item["title"], item["album"], item["artist"], item["quality"]
        )

    console.print(table)
    choice = input(f"\n📥 请输入序号 (1-{len(results)})，0 退出: ")
    if choice.isdigit() and 0 < int(choice) <= len(results):
        selected = results[int(choice) - 1]
        downloader.process_track(selected["id"], download_dir)
