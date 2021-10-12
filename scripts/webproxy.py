"""
Reverse proxy code adapted from:
https://github.com/oetiker/aio-reverse-proxy/blob/master/paraview-proxy.py'
(Copyright (c) 2018 Tobias Oetiker, MIT License)
"""

from aiohttp import web
from aiohttp import client
import aiohttp_cors
import aiohttp
import asyncio
import logging
import pprint

#logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import argparse
parser = argparse.ArgumentParser()
parser.add_argument(
  "port",
  help="Port to listen to",
  type=int
)
parser.add_argument(
  "http",
  help="URL to forward HTTP requests to",
  type=str,
)

parser.add_argument(
  "ws",
  help="URL to forward WebSocket requests to",
  type=str,
)

args = parser.parse_args()

if not args.http.startswith("http://"):
    if args.http.startswith("https://"):
        raise ValueError("HTTP URL must start with http://, HTTPS not supported")
    raise ValueError("HTTP URL must start with http://")

if not args.ws.startswith("ws://"):
    if args.ws.startswith("wss://"):
        raise ValueError("WebSocket URL must start with ws://, WSS not supported")
    raise ValueError("WebSocket URL must start with ws://")


async def handler(req):
    tail = req.match_info.get('tail')
    reqH = req.headers.copy()
    
    # handle the websocket request
    
    if reqH.get('connection') == 'Upgrade' and reqH.get('upgrade') == 'websocket' and req.method == 'GET':

      ws_server = web.WebSocketResponse()
      await ws_server.prepare(req)
      logger.info('##### WS_SERVER %s' % pprint.pformat(ws_server))

      client_session = aiohttp.ClientSession(cookies=req.cookies)
      url = args.ws.strip("/") + "/" + tail
      async with client_session.ws_connect(
        url,
      ) as ws_client:
        logger.info('##### WS_CLIENT %s' % pprint.pformat(ws_client))

        async def ws_forward(ws_from,ws_to):
          async for msg in ws_from:
            #logger.info('>>> msg: %s',pprint.pformat(msg))
            mt = msg.type
            md = msg.data
            if mt == aiohttp.WSMsgType.TEXT:
              await ws_to.send_str(md)
            elif mt == aiohttp.WSMsgType.BINARY:
              await ws_to.send_bytes(md)
            elif mt == aiohttp.WSMsgType.PING:
              await ws_to.ping()
            elif mt == aiohttp.WSMsgType.PONG:
              await ws_to.pong()
            elif ws_to.closed:
              await ws_to.close(code=ws_to.close_code,message=msg.extra)
            else:
              raise ValueError('unexpected message type: %s',pprint.pformat(msg))

        # keep forwarding websocket data in both directions
        await asyncio.wait([ws_forward(ws_server,ws_client),ws_forward(ws_client,ws_server)],return_when=asyncio.FIRST_COMPLETED)

        return ws_server
    else:
      # handle normal requests by passing them on downstream
      url = args.http.strip("/") + "/" + tail
      async with client.request(
          req.method, url,
          headers = reqH,
          params=req.query,
          allow_redirects=False,
          data = await req.read()
      ) as res:
          headers = res.headers.copy()
          body = await res.read()
          return web.Response(
            headers = headers,
            status = res.status,
            body = body
          )

app = web.Application(
    client_max_size=1024**3
)
app.add_routes([
    web.get('/{tail:.*}', handler),
    web.put('/{tail:.*}', handler),
    web.patch('/{tail:.*}', handler),
])

cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods=["GET", "PATCH", "PUT"]
        )
})

# Configure CORS on all routes.
for route in list(app.router.routes()):
    cors.add(route)    

if __name__ == "__main__":
    web.run_app(app,port=args.port)
