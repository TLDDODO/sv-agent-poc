import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(
        command='/home/ychen/.local/bin/uvx',
        args=['--from', 'pdbe-mcp-server', 'pdbe-mcp-server', '--server-type', 'pdbe_search_server', '--transport', 'stdio'],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(json.dumps([{'name': t.name, 'description': t.description, 'inputSchema': t.inputSchema} for t in tools.tools], indent=2))
asyncio.run(main())
