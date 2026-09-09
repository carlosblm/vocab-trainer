"""Punto de entrada de la interfaz de línea de comandos."""

import sys

from vocab.config import get_settings


def main() -> None:
    settings = get_settings()
    print(f"vocab-trainer · F0 · Python {sys.version.split()[0]}")
    print(f"DATABASE_URL = {settings.database_url}")


if __name__ == "__main__":
    main()
