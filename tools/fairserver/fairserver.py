"""
Fair server requests:
Human and machine. For now, just machine.
If unknown, just return 404.
The server keeps nothing in memory, content is just served by
opening files again and again.

1. /machine/page/<name of fairpage>
- Description
- Link to web page
- List of entries. Each entry:
  - checksum: deep checksum
  - type: deep cell or dataset
  - version number (only required if no date)
  - date (only required if no version number)
  - format (optional. for example, mmcif for pdb)
  - compression (optional. Can be gzip, zip, bzip2)
  - latest: yes or no. For a given format+compression, only one entry can be latest.
  - index_size: size of the deep buffer itself
  - nkeys: number of keys
  - content_size: see above.
  - keyorder: checksum 
  - download_index: checksum (if available)
Response is built dynamically by parsing:
$FD/page_entries/<page_name>.json and $FD/page_header/<page_name>.cson/.json/.yaml
2. /machine/find/<checksum>
   Response:
   - name of fairpage
   - fairpage entry (see above)
3. /machine/deepbuffer/<checksum>
   Deep buffer (= element index) content. 
   Dict of element-to-elementchecksum
4. /machine/download/<element-checksum>
   List of URLS for that element.
5. /machine/keyorder/<keyorder checksum>
   Key order buffer (list of key orders) content.
6. /machine/get_entry?page=...&version=...&date=...
   /machine/get_checksum?page=...&version=...&date=...
"""

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

async def get_entries(fairpage):
    filename = os.path.join(FD, "page_entries", fairpage + ".json")
    async with aiofiles.open(filename, mode='r') as f:
        entries = await f.read()
    entries = cson.loads(entries)
    return entries

async def handle_machine_fairpage(request):
    fairpage = request.match_info.get('fairpage')
    
    try:
        entries = await get_entries(fairpage)
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
        body=json.dumps(fairpage_content, indent=2)+"\n",
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
        body=json.dumps(result, indent=2)+"\n",
        content_type='application/json'
    )

_download_index_cache = {}
# NOTE: in production, maybe empty a cache item after some idle time,
#  and/or limit to a maximum amount of cache memory...
async def handle_machine_download(request):
    checksum = request.match_info.get('checksum')
    try:
        download_index_files = glob.glob(os.path.join(FD, "download_index", "*"))
        for filename in download_index_files:
            if filename in _download_index_cache:
                download_index = _download_index_cache[filename]
            else:
                async with aiofiles.open(filename) as f:
                    data = await f.read()
                download_index = json.loads(data)
                _download_index_cache[filename] = download_index
            try:
                urls = download_index[checksum]
                break
            except KeyError:
                pass
        else:
            raise KeyError(checksum)
    except Exception:
        traceback.print_exc()    
        return web.Response(
            status=404,
            body=json.dumps({'not found': 404}),
            content_type='application/json'
        )
    return web.Response(
        status=200,
        body=json.dumps(urls, indent=2)+"\n",
        content_type='application/json'
    )

def get_page_params(request):    
    page = request.query.get("page")
    if page is None:
        return web.Response(
            status=400,
            text="parameter 'page' undefined\n",
        )
    params = {}
    for param in ("type", "version", "date", "compression", "format"):
        p = request.query.get(param)
        if p is not None:
            if p == "none":
                params[param] = None            
            else:
                params[param] = p    
    return page, params


async def get_entry(page, params):
    entries = await get_entries(page)
    version, date = params.get("version"), params.get("date")
    if version is None and date is None:
        entries = [e for e in entries if e.get("latest")]
        to_filter = ("type", "format", "compression")
    else:
        to_filter = ("type", "version", "date", "format", "compression")
    for param in to_filter:
        if param not in params:
            continue
        p = params[param]  # can be None
        if param in ("compression", "format"):
            default = None
        else:
            default = p      
        entries = [e for e in entries if e.get(param, default) == p]
    if len(entries) == 0:
        return web.Response(
            status=400,
            text="No entry with the given parameters\n",
        )
    elif len(entries) > 1:
        # If compression was not specified, and one of the entries has no compression, return it
        if "compression" not in params:
            entries2 = [e for e in entries if e.get("compression", None) is None]
            if len(entries2) == 1:
                return entries2[0]
        text = "Multiple entries with given parameters:\n\n"
        text += json.dumps(entries, indent=2)
        text += "\n\n({} entries)\n".format(len(entries))
        return web.Response(
            status=300,
            text=text
        )
    entry = entries[0]
    return entry

async def handle_get_entry(request):
    page_params = get_page_params(request)
    if isinstance(page_params, web.Response):
       err = page_params
       return err
    page, params = page_params
    entry = await get_entry(page, params)
    if isinstance(entry, web.Response):
       err = entry
       return err
    return web.Response(
        status=200,
        body=json.dumps(entry, indent=2)+"\n",
        content_type='application/json'
    )

async def handle_get_checksum(request):
    page_params = get_page_params(request)
    if isinstance(page_params, web.Response):
       err = page_params
       return err
    page, params = page_params
    entry = await get_entry(page, params)
    if isinstance(entry, web.Response):
       err = entry
       return err
    return web.Response(
        status=200,
        text=entry["checksum"] + "\n"
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
        web.get('/machine/download/{checksum:.*}', handle_machine_download),
        web.get('/machine/deepbuffer/{tail:.*}', partial(handle_static, "deepbuffer")),
        web.get('/machine/keyorder/{tail:.*}', partial(handle_static, "keyorder")),
        web.get('/machine/get_entry', handle_get_entry),
        web.get('/machine/get_checksum', handle_get_checksum),
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