import asyncio
from .cli import cli_parser

if __name__ == "__main__":
    asyncio.run(cli_parser())
