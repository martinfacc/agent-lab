import asyncio


async def copy_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()


async def forward(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
) -> None:
    try:
        server_reader, server_writer = await asyncio.open_connection("127.0.0.1", 9120)
        await asyncio.gather(
            copy_stream(client_reader, server_writer),
            copy_stream(server_reader, client_writer),
        )
    except (ConnectionError, OSError):
        client_writer.close()


async def main() -> None:
    server = await asyncio.start_server(forward, "0.0.0.0", 9119)
    async with server:
        await server.serve_forever()


asyncio.run(main())
