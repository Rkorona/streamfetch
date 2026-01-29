import logging
from rich.logging import RichHandler
from rich.console import Console

console = Console()


def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, console=console, show_path=False)],
    )
    return logging.getLogger("streamfetch")


logger = setup_logging()
