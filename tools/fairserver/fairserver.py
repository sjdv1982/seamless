from aiohttp import web
import aiohttp_cors
import json
import aiofiles
import os
import cson
import traceback
from ruamel.yaml import YAML
import glob
from functools import partial
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
        for entry in entries:
            entry.pop("raw_download_indices", None)
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

# NOTE: in production, you will want to cache the fairpages, 
# or even cache a checksum-to-entry dict
async def handle_machine_find(request):
    checksum = request.match_info.get('checksum')
    
    try:
        fairpages = glob.glob(os.path.join(FD, "page_entries", "*.json"))
        for filename in fairpages:
            fairpage = os.path.split(filename)[1].split(".")[0]
            async with aiofiles.open(filename, mode='r') as f:
                entries = await f.read()
            entries = cson.loads(entries)
            for entry in entries:
                if entry["checksum"] == checksum:
                    break
            else:
                continue
            break
        else:
            raise KeyError(checksum)
    except Exception:
        traceback.print_exc()    
        return web.Response(
            status=404,
            body=json.dumps({'not found': 404}),
            content_type='application/json'
        )
    
    result = {
        "fairpage": fairpage,
        "entry": entry
    }
    return web.Response(
        status=200,
        body=json.dumps(result, indent=2),
        content_type='application/json'
    )

# NOTE: in production, send this to NGINX/Apache instead
async def handle_static(head, request):
    tail = request.match_info.get('tail')
    filename = os.path.join(FD, head, tail)
    if not os.path.exists(filename):
        return web.Response(
            status=404,
            body=json.dumps({'not found': 404}),
            content_type='application/json'
        )
    with open(filename, "rb") as f:
        buf = f.read()
    response = web.Response(status=200, body=buf)
    response.enable_compression()
    return response

def main():
    app = web.Application(
        client_max_size=1024**3,
    )
    app.add_routes([
        web.get('/machine/page/{fairpage:.*}', handle_machine_fairpage),
        web.get('/machine/find/{checksum:.*}', handle_machine_find),
        web.get('/machine/download_index/{tail:.*}', partial(handle_static, "download_index")),
        web.get('/machine/deepbuffer/{tail:.*}', partial(handle_static, "deepbuffer")),
        web.get('/machine/keyorder/{tail:.*}', partial(handle_static, "keyorder")),
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