def main():
    import asyncio
    from .cli import cli_parser

    asyncio.run(cli_parser())
