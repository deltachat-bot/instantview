"""Bot to get web previews in chats"""

from .hooks import cli


def main() -> None:
    """Start the CLI application."""
    try:
        cli.start()
    except KeyboardInterrupt:
        pass
