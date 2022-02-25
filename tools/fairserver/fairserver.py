"""
Fair server requests:
Human and machine. For now, just machine.
If unknown, just return 400.
The server keeps nothing in memory, content is just served by
opening files again and again.

1. /machine/dataset/<name of dataset>
- Description
- Link to web page
- List of distributions. Each distribution:
  - checksum: deep checksum
  - type: deepcell or deepfolder
  - version number (only required if no date)
  - date (only required if no version number)
  - format (optional. for example, mmcif for pdb)
  - compression (optional. Can be gzip, zip, bzip2)
  - latest: True, or absent. For a given format+compression, only one distribution can be latest.
  - index_size: size of the deep buffer itself
  - nkeys: number of keys
  - content_size: see above.
  - keyorder: checksum 
  - access_index: checksum (if available)
    The access_index file is not normally shared by the FAIRserver,
    but if it can be obtained elsewhere, it can be useful for mass-downloading.
Response is built dynamically by parsing:
$FD/dataset_distributions/<dataset_name>.json and $FD/dataset_header/<dataset_name>.cson/.json/.yaml
2. /machine/find/<checksum>
   Response:
   - name of dataset
   - dataset distribution (see above)
3. /machine/deepbuffer/<checksum>
   Deep buffer (= element index) content. 
   Dict of element-to-elementchecksum
4. /machine/access/<element-checksum>
   List of URLS for that element.
5. /machine/keyorder/<keyorder checksum>
   Key order buffer (list of key orders) content.
6. /machine/find_distribution?dataset=...&version=...&date=...
   /machine/find_checksum?dataset=...&version=...&date=...
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
import copy
yaml = YAML(typ='safe')

PORT=61918 # F-A-I-R

def err(*args, **kwargs):
    print("ERROR: " + args[0], *args[1:], **kwargs)
    exit(1)

FD = os.environ.get("FAIRSERVER_DIR")
if FD is None:
    err("FAIRSERVER_DIR undefined")

async def get_distributions(dataset):
    filename = os.path.join(FD, "dataset_distributions", dataset + ".json")
    async with aiofiles.open(filename, mode='r') as f:
        distributions = await f.read()
    distributions = cson.loads(distributions)
    return distributions

async def handle_machine_dataset(request):
    dataset = request.match_info.get('dataset')
    
    try:
        distributions = await get_distributions(dataset)
        loaders = {
            "json": cson.loads,
            "cson": cson.loads,
            "yaml": yaml.load
        }
        for ext in loaders.keys():
            filename = os.path.join(FD, "dataset_header", dataset + "." + ext)
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
    
    dataset_content = header
    dataset_content["distributions"] = distributions
    return web.Response(
        status=200,
        body=json.dumps(dataset_content, indent=2)+"\n",
        content_type='application/json'
    )

# NOTE: in production, you will want to cache the datasets, 
# or even cache a checksum-to-distribution dict
async def handle_machine_find(request):
    checksum = request.match_info.get('checksum')
    
    try:
        datasets = glob.glob(os.path.join(FD, "dataset_distributions", "*.json"))
        for filename in datasets:
            dataset = os.path.split(filename)[1].split(".")[0]
            async with aiofiles.open(filename, mode='r') as f:
                distributions = await f.read()
            distributions = cson.loads(distributions)
            for distribution in distributions:
                if distribution["checksum"] == checksum:
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
        "dataset": dataset,
        "distribution": distribution
    }
    return web.Response(
        status=200,
        body=json.dumps(result, indent=2)+"\n",
        content_type='application/json'
    )

_access_index_cache = {}
# NOTE: in production, maybe empty a cache item after some idle time,
#  and/or limit to a maximum amount of cache memory...
async def handle_machine_access(request):
    checksum = request.match_info.get('checksum')
    try:
        access_index_files = glob.glob(os.path.join(FD, "access_index", "*"))
        for filename in access_index_files:
            if filename in _access_index_cache:
                access_index = _access_index_cache[filename]
            else:
                async with aiofiles.open(filename) as f:
                    data = await f.read()
                access_index = json.loads(data)
                _access_index_cache[filename] = access_index
            try:
                urls = access_index[checksum]
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

def get_dataset_params(request):    
    dataset = request.query.get("dataset")
    if dataset is None:
        return web.Response(
            status=400,
            text="parameter 'dataset' undefined\n",
        )
    params = {}
    for param in ("type", "version", "date", "compression", "format"):
        p = request.query.get(param)
        if p is not None:
            if p == "none":
                params[param] = None            
            else:
                params[param] = p    
    return dataset, params


async def find_distribution(dataset, params):
    distributions = await get_distributions(dataset)
    version, date = params.get("version"), params.get("date")
    if version is None and date is None:
        distributions = [e for e in distributions if e.get("latest")]
        to_filter = ("type", "format", "compression")
    else:
        to_filter = ("type", "version", "date", "format", "compression")
    for param in to_filter:
        if param not in params:
            continue
        p = params[param]  # can be None
        default = None
        if param == "version" and p == "latest":
            param = "latest"
            p = True     
            default = False
        distributions = [e for e in distributions if e.get(param, default) == p]
    if len(distributions) == 0:
        return web.Response(
            status=300,
            text="No distribution with the given parameters\n",
        )
    elif len(distributions) > 1:
        # If compression was not specified, and one of the distributions has no compression, return it
        if "compression" not in params:
            distributions2 = [e for e in distributions if e.get("compression", None) is None]
            if len(distributions2) == 1:
                return distributions2[0]
        text = "Multiple distributions with given parameters:\n\n"
        dist = copy.deepcopy(distributions)
        attrs = ("type", "date", "format", "compression", "latest")
        for d in dist:
            for k in list(d.keys()):
                if k not in attrs:
                    d.pop(k)
        text += json.dumps(dist, indent=2)
        text += "\n\n({} distributions)\n".format(len(distributions))
        return web.Response(
            status=300,
            text=text
        )
    distribution = distributions[0]
    return distribution

async def handle_get_distribution(request):
    dataset_params = get_dataset_params(request)
    if isinstance(dataset_params, web.Response):
       err = dataset_params
       return err
    dataset, params = dataset_params
    distribution = await find_distribution(dataset, params)
    if isinstance(distribution, web.Response):
       err = distribution
       return err
    return web.Response(
        status=200,
        body=json.dumps(distribution, indent=2)+"\n",
        content_type='application/json'
    )

async def handle_get_checksum(request):
    dataset_params = get_dataset_params(request)
    if isinstance(dataset_params, web.Response):
       err = dataset_params
       return err
    dataset, params = dataset_params
    distribution = await find_distribution(dataset, params)
    if isinstance(distribution, web.Response):
       err = distribution
       return err
    return web.Response(
        status=200,
        text=distribution["checksum"] + "\n"
    )

        



# NOTE: in production, send this to NGINX/Apache instead
async def handle_static(head, request):
    tail = request.match_info.get('tail')
    filename = os.path.join(FD, head, tail)
    if not os.path.exists(filename):
        return web.Response(
            status=400,
            body=json.dumps({'not found': 400}),
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
        web.get('/machine/dataset/{dataset:.*}', handle_machine_dataset),
        web.get('/machine/find/{checksum:.*}', handle_machine_find),
        web.get('/machine/access/{checksum:.*}', handle_machine_access),
        web.get('/machine/deepbuffer/{tail:.*}', partial(handle_static, "deepbuffer")),
        web.get('/machine/keyorder/{tail:.*}', partial(handle_static, "keyorder")),
        web.get('/machine/find_distribution', handle_get_distribution),
        web.get('/machine/find_checksum', handle_get_checksum),
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