from aiohttp import web
import aiohttp_cors
import json
import aiofiles
import os
import cson
import traceback
from ruamel.yaml import YAML
yaml = YAML(typ='safe')


PORT=61918 # F-A-I-R

def err(*args, **kwargs):
    print("ERROR: " + args[0], *args[1:], **kwargs)
    exit(1)

FD = os.environ.get("FAIRSERVER_DIR")
if FD is None:
    err("FAIRSERVER_DIR undefined")

async def handle_machine_fairpage(request):
    fairpage = request.match_info.get('fairpage')
    
    try:
        filename = os.path.join(FD, "page_entries", fairpage + ".json")
        #$FD/page_entries/<page_name>.json and $FD/page_header/<page_name>.cson/.json/.yaml
        async with aiofiles.open(filename, mode='r') as f:
            entries = await f.read()
            entries = cson.loads(entries)
        loaders = {
            "json": cson.loads,
            "cson": cson.loads,
            "yaml": yaml.load
        }
        for ext in loaders.keys():
            filename = os.path.join(FD, "page_header", fairpage + "." + ext)
            if os.path.exists(filename):
                loader = loaders[ext]
                async with aiofiles.open(filename, mode='r') as f:
                    header = await f.read()
                header = loader(header)
                break
        else:
            raise FileNotFoundError
    except Exception:
        traceback.print_exc()    
        return web.Response(
            status=404,
            body=json.dumps({'not found': 404}),
            content_type='application/json'
        )
    
    fairpage_content = header
    fairpage_content["entries"] = entries
    return web.Response(
        status=200,
        body=json.dumps(fairpage_content, indent=2),
        content_type='application/json'
    )

def main():
    app = web.Application(
        client_max_size=1024**3,
    )
    app.add_routes([
        web.get('/machine/page/{fairpage:.*}', handle_machine_fairpage),
        # ....
    ])

    # Configure default CORS settings.
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods=["GET"]
            )
    })

    # Configure CORS on all routes.
    for route in list(app.router.routes()):
        cors.add(route)

    web.run_app(app,port=PORT)

if __name__ == "__main__":
    main()    