ADDRESS = '127.0.0.1'
PORT = 8700

import os
os.environ["SEAMLESS_COMMUNION_ID"] = "jobmaster-service"
os.environ["SEAMLESS_COMMUNION_OUTGOING"] = "8600"
import seamless
seamless.set_ncores(0)

from seamless import communionserver
communionserver.configure_master(
    value=True,
    transformer_job=True,
    transformer_result=True,
    transformer_result_level2=True
)

from seamless.highlevel import load_graph
import sys, json

from aiohttp import web
import aiohttp_cors

redis_cache = seamless.RedisCache()

async def handler(request):
    text = await request.text()
    graph = json.loads(text)
    ctx = load_graph(graph)
    ctx.equilibrate()
    colored_graph = ctx.get_graph()
    body = json.dumps(colored_graph, indent=2, sort_keys=True) 
    return web.Response(
        status=200,
        body=body,
        content_type='application/json',
    )            

async def start():
    await communionserver._start()
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

