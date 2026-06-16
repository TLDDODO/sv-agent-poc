import asyncio
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(command='/home/ychen/.local/bin/uvx', args=['--from','pdbe-mcp-server','pdbe-mcp-server','--server-type','pdbe_search_server','--transport','stdio'])
    payload = {
        'query': 'title:*EGFR* AND title:*T790M*',
        'fl': ['pdb_id','title','resolution','experimental_method','ligand_name'],
        'fq': ['resolution:[0 TO 3.5]'],
        'sort': 'resolution asc',
        'rows': 10,
    }
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool('run_pdbe_search_query', payload)
            text = '\n'.join([getattr(c, 'text', str(c)) for c in result.content])
            Path('outputs/pdbe_egfr_t790m_title_search.txt').write_text(text, encoding='utf-8')
            print(text[:4000])
asyncio.run(main())
