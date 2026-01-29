from pathlib import Path
from streamfetch.tidal.api import TidalApi
from streamfetch.tidal.downloader import TidalDownloader
from streamfetch.cli.interactive import interactive_search
from streamfetch.utils.filename import sanitize_filename


def handle_command(base_url, command, value):
    download_dir = Path.cwd() / "downloads"
    download_dir.mkdir(exist_ok=True)

    api = TidalApi(base_url)
    downloader = TidalDownloader(api)

    if command == "search":
        interactive_search(api, downloader, value, download_dir)
    elif command == "track":
        downloader.process_track(value, download_dir)
    elif command == "album":
        data = api.get_album(value)
        album_dir = download_dir / sanitize_filename(
            f"{data['albumInfo'].get('title')} - {
                data['albumInfo'].get('artist', {}).get('name')
            }"
        )
        album_dir.mkdir(exist_ok=True)
        for track in data["tracks"]:
            downloader.process_track(track["id"], album_dir)
