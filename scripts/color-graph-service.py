ADDRESS = '127.0.0.1'
PORT = 8700

import os
os.environ["SEAMLESS_COMMUNION_ID"] = "jobmaster-service"
os.environ["SEAMLESS_COMMUNION_OUTGOING"] = "8600"
import seamless
seamless.set_ncores(0)

from seamless import communion_server
communion_server.configure_master(
    buffer=True,
    buffer_status=True,
    transformation_job=True,
    transformation_status=True,
)

from seamless.highlevel import load_graph
import sys, json

from aiohttp import web
import aiohttp_cors

seamless.database_cache.connect()

async def handler(request):
    text = await request.text()
    graph = json.loads(text)
    ctx = load_graph(graph)
    await ctx.computation()
    colored_graph = ctx.get_graph()
    body = json.dumps(colored_graph, indent=2, sort_keys=True)
    return web.Response(
        status=200,
        body=body,
        content_type='application/json',
    )

async def start():
    await communion_server._start()
    app = web.Application()
    app.add_routes([
        web.get('/{tail:.*}', handler),
    ])

    # Configure default CORS settings.
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods=["GET", ]
            )
    })

    # Configure CORS on all routes.
    for route in list(app.router.routes()):
        cors.add(route)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, ADDRESS, PORT)
    await site.start()

import asyncio
asyncio.ensure_future(start())

loop = asyncio.get_event_loop()
if len(sys.argv) > 1:
    run_time = float(sys.argv[1])
    loop.call_later(run_time, sys.exit)
loop.run_forever()
