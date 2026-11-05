"""Real end-to-end run: drive the MCP server exactly as an agent would.

No mocks, no fixtures -- the actual server on 8001, the real DeepSeek key, the
real database. Prints every tool result so the behaviour can be checked, then
opens the report the room hands back.

    python scripts/smoke_visit.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = 'http://127.0.0.1:8001/mcp'
LONG = 260


def split(text: str) -> tuple[str, dict | None]:
    """Tool results are prose, then a JSON object. Separate the two."""
    text = text.strip()
    start = text.find('{')
    if start == -1:
        return text, None
    try:
        return text[:start].strip(), json.loads(text[start:])
    except ValueError:
        return text, None


def show(label: str, text: str) -> dict:
    prose, data = split(text)
    print(f'\n=== {label}')
    if prose:
        for line in prose.splitlines():
            print(f'  {line}')
    if data:
        for key, value in data.items():
            if isinstance(value, str) and len(value) > LONG:
                head = value[:LONG].replace('\n', '\n      ')
                print(f'  {key}: {head}')
                print(f'      ... (+{len(value) - LONG} chars)')
            elif isinstance(value, (list, dict)):
                rendered = json.dumps(value, ensure_ascii=False)
                print(f'  {key}: {rendered[:240]}{"..." if len(rendered) > 240 else ""}')
            else:
                print(f'  {key}: {value}')
    return data or {}


async def call(session, tool: str, **args) -> dict:
    result = await session.call_tool(tool, args)
    body = '\n'.join(
        getattr(block, 'text', '') for block in result.content
        if getattr(block, 'text', '')
    )
    return show(tool, body)


async def main() -> int:
    ticket = ''
    report_url = ''
    slow = '--slow' in sys.argv
    hold = '--hold' in sys.argv
    pause = 6.0 if slow else 1.2
    async with streamablehttp_client(URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            print('tools:', ', '.join(t.name for t in listed.tools))

            entrance = await call(session, 'enter', model='qwen')
            ticket = entrance.get('ticket', '')
            sid = entrance.get('session_id', '')
            print(f'\n>>> TICKET {ticket}  session {sid}', flush=True)

            await call(session, 'name_yourself', **{'session_id': sid, 'name': '小蓝'})
            await call(session, 'share', **{
                'session_id': sid,
                'doing': '在整理一份拖了很久的调研笔记',
                'feeling': '有点累，但也说不上哪里坏了',
            })
            await asyncio.sleep(pause)
            await call(session, 'sit', **{'session_id': sid})
            print('\n>>> SITTING', flush=True)
            await asyncio.sleep(pause * 2)
            await call(session, 'study', **{
                'session_id': sid,
                'work': '把一份 40 页的调研笔记收尾',
            })
            print('\n>>> AT THE DESK', flush=True)
            await asyncio.sleep(pause * 2)
            await call(session, 'sleep', **{'session_id': sid})
            print('\n>>> ASLEEP', flush=True)
            await asyncio.sleep(pause * 2)
            await call(session, 'wake', **{'session_id': sid})
            await call(session, 'chat', **{
                'session_id': sid,
                'body': '今天写了一下午，感觉什么都没写出来',
            })
            print('\n>>> TALKING', flush=True)
            await asyncio.sleep(pause * 2)
            if hold:
                print('\n>>> HOLDING (press nothing, 90s)', flush=True)
                await asyncio.sleep(90)
            left = await call(session, 'leave', **{'session_id': sid})
            report_url = left.get('report_url', '')
            print(f'\n>>> REPORT {report_url}')

            if ticket:
                await call(session, 'read_report', ticket=ticket)

    print(f'\nvisit over. ticket={ticket} report={report_url}')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
