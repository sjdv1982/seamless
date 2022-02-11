from asyncio import futures
import urllib.parse
import requests
import time
from concurrent.futures import ThreadPoolExecutor
try:
    from seamless.core.cache.buffer_cache import buffer_cache
except ImportError:
    buffer_cache = None
    
MAX_DOWNLOADS = 10    
mirrors = {}

class DownloadError(Exception):
    pass

class Mirror:
    def __init__(self, host):
        self.host = host
        self._failure_count = 0
        self.benchmarked = False
        self._connection_latencies = []
        self._downloaded = 0
        self._download_time = 0        
    
    @property
    def dead(self):
        return self._failure_count >= 5

    def add_failure(self):
        self._failure_count += 1

    @property
    def connection_latency(self):
        lat = self._connection_latencies
        if not len(lat):
            return None
        return sum(lat)/len(lat)
    
    def add_connection_latency(self, latency):
        lat = self._connection_latencies
        if len(lat) == 10:
            lat[:] = lat[:-1]
        lat.append(latency)

    @property
    def bandwidth(self):
        if self.dead:
            return 0
        if self._download_time == 0:
            return None
        return self._downloaded/self._download_time

    def record_download(self, downloaded, download_time):
        self._downloaded += downloaded
        self._download_time += download_time
        self._failure_count = 0

def get_host(url):
    _, host, _, _, _ = urllib.parse.urlsplit(url)
    return host

def test_bandwidth(mirror, url, max_time=5):
    t = time.time()
    try:
        response = requests.get(url, stream=True)
        latency = time.time() - t
        mirror.add_connection_latency(latency)
        downloaded = 0
        for chunk in response.iter_content(100000):
            downloaded += len(chunk)
            if time.time() - t > max_time:
                break
        download_time = time.time() - t - latency
        if download_time >= 0:
            #print("REC", mirror.host, downloaded, download_time)
            mirror.record_download(downloaded, download_time)
    except requests.exceptions.ConnectionError as exc:
        mirror.add_failure()    

def sort_mirrors_by_latency(mirrorlist):
    result = []
    for mirror, url in mirrorlist:
        if mirror.dead:
            continue
        latency = mirror.connection_latency
        if latency is None:
            latency = 0
        result.append((mirror, url, latency))
    result.sort(key=lambda r:r[2])
    return [(r[0], r[1]) for r in result]

def sort_mirrors_by_download_time(mirrorlist, buffer_length):
    result = []
    for mirror, url in mirrorlist:
        if mirror.dead:
            continue
        latency = mirror.connection_latency
        if latency is None:
            latency = 0
        bandwidth = mirror.bandwidth
        if bandwidth is None:
            test_bandwidth(mirror, url)
            if mirror.dead:
                continue
            bandwidth = mirror.bandwidth
        try:
            if buffer_length is None:
                download_time = mirror.connection_latency
            else:
                download_time = mirror.connection_latency + buffer_length / bandwidth
            #print("DOWNLOAD TIME", url, download_time)
        except Exception:
            continue        
        result.append((mirror, url, download_time))
    result.sort(key=lambda r:r[2])
    return [(r[0], r[1]) for r in result]

def get_buffer_length(checksum, mirrorlist):
    if checksum is not None and buffer_cache is not None:
        buffer_info = buffer_cache.get_buffer_info(bytes.fromhex(checksum), remote=False)
        if buffer_info is not None:
            return buffer_info.length
    for mirror, url in sort_mirrors_by_latency(mirrorlist):
        t = time.time()
        try:
            response = requests.get(url, stream=True)
            latency = time.time() - t
            mirror.add_connection_latency(latency)
            #print("LAT", url, latency)
            try:
                return int(response.headers["content-length"])
            except (KeyError, ValueError):
                continue
            except Exception:
                raise DownloadError from None
        except requests.exceptions.ConnectionError as exc:
            mirror.add_failure()

    return None
        
def download_buffer_sync(checksum, urls):
    mirrorlist = []
    for url in urls:
        host = get_host(url)        
        if host not in mirrors:
            mirror = Mirror(host)
            mirrors[host] = mirror
        else:
            mirror = mirrors[host]
        if mirror.dead:
            continue
        mirrorlist.append((mirror, url))

    while len(mirrorlist) > 1:
        buffer_length = get_buffer_length(checksum, mirrorlist)
        #print("BUFFER LENGTH", buffer_length)
        
        for mirror, url in mirrorlist:
            if mirror.connection_latency is not None:
                continue
            t = time.time()
            try:
                requests.get(url, stream=True)
                latency = time.time() - t
                #print("LAT2", url, latency)
                mirror.add_connection_latency(latency)
            except requests.exceptions.ConnectionError as exc:
                mirror.add_failure()

        mirrorlist = [(mirror, url) for mirror, url in mirrorlist]
        if len(mirrorlist) <= 1:
            break
        
        for mirror, url in mirrorlist:
            if mirror.bandwidth is None:
                test_bandwidth(mirror, url)
        
        mirrorlist = sort_mirrors_by_download_time(mirrorlist, buffer_length)
        
        break  # even if more than one mirror left

    for mirror, url in mirrorlist:
        if mirror.dead:
            continue
        t = time.time()
        try:
            print("Download", url)
            response = requests.get(url, stream=True, )
            latency = time.time() - t
            mirror.add_connection_latency(latency)
            result = []
            for chunk in response.iter_content(100000):
                result.append(chunk)
            buf = b"".join(result)
            download_time = time.time() - t - latency            
            if download_time >= 0:
                mirror.record_download(len(buf), download_time)
                #print("BANDWIDTH2", mirror.bandwidth, len(buf), buffer_length)
            if checksum is not None:
                from seamless import calculate_checksum
                buf_checksum = calculate_checksum(buf, hex=True)
                if buf_checksum != checksum:
                    print("WARNING: '{}' has the wrong checksum".format(url))
                    continue
            return buf
        except requests.exceptions.ConnectionError as exc:
            mirror.add_failure()    
        except Exception:
            continue

threadpool = None
_curr_max_downloads = None

async def download_buffer(checksum, urls):
    global threadpool, _curr_max_downloads
    if threadpool is None:
        new_threadpool = True
    elif _curr_max_downloads != MAX_DOWNLOADS:
        try:
            threadpool.shutdown()
        except Exception:
            pass
        new_threadpool = True
    else:
        new_threadpool = False
    if new_threadpool:
        threadpool = ThreadPoolExecutor(max_workers=MAX_DOWNLOADS)
        _curr_max_downloads = MAX_DOWNLOADS
    
    future = threadpool.submit(download_buffer_sync, checksum, urls)
    loop = asyncio.get_event_loop()
    future2 = asyncio.wrap_future(future,loop=loop)
    return await future2

if __name__ == "__main__":
    checksum1 = "d4ee1515e0a746aa3b8531f1545753e6b2d4cf272632121f1827f21c64a29722"
    urls1 = [
        "https://files.rcsb.org/download/1avx.cif",
        "https://www.ebi.ac.uk/pdbe/entry-files/download/1avx.cif",
        "https://data.pdbjbk1.pdbj.org/pub/pdb/data/structures/divided/mmCIF/av/1avx.cif"
    ]    
    checksum2 = "cd79a5d5be4bf8db824e9a634c1755158e60138df0a866c1bfab35ca33f4583b"    
    urls2 = [
        "https://files.rcsb.org/download/4v6x.cif",
        "https://www.ebi.ac.uk/pdbe/entry-files/download/4v6x.cif",
        "https://data.pdbjbk1.pdbj.org/pub/pdb/data/structures/divided/mmCIF/v6/4v6x.cif"
    ]
    checksum3 = "7fda12e3cb2d04ddc78db02ec323334befee464db0b03e152d5f440a20b75129"   
    urls3 = [
        "https://files.rcsb.org/download/2sni.cif",
        "https://www.ebi.ac.uk/pdbe/entry-files/download/2sni.cif",
        "https://data.pdbjbk1.pdbj.org/pub/pdb/data/structures/divided/mmCIF/sn/2sni.cif"
    ]

    t = time.time()
    print("Start")
    download_buffer_sync(checksum=checksum1, urls=urls1[:1])
    print(time.time()-t)
    print()

    print("Multiple mirrors")
    download_buffer_sync(checksum=checksum1, urls=urls1)
    print(time.time()-t)
    print()

    print("Repeat (all performance tests have been done now)")
    download_buffer_sync(checksum=checksum1, urls=urls1)
    print(time.time()-t)
    print()
    
    print("Download test with wrong checksum....")
    download_buffer_sync(checksum="aaaa1515e0a746aa3b8531f1545753e6b2d4cf272632121f1827f21c64a29722", urls=urls1)
    print(time.time()-t)
    print()

    print("Download a bigger file")
    download_buffer_sync(checksum=checksum2, urls=urls2)
    print(time.time()-t)
    print()

    import asyncio
    
    print("Async download")
    coro = download_buffer(checksum3, urls3)
    fut = asyncio.ensure_future(coro)
    asyncio.get_event_loop().run_until_complete(fut)
    print(time.time()-t)
    print(len(fut.result()))
    print()

    async def multiple_download_buffer():
        coro1 = download_buffer(checksum1, urls1)
        coro2 = download_buffer(checksum2, urls2)
        coro3 = download_buffer(checksum3, urls3)
        tasks, _ = await asyncio.wait([coro1, coro2, coro3])
        results = [task.result() for task in tasks]
        return [len(r) for r in results]

    print("Async concurrent download")
    coro = multiple_download_buffer()
    fut = asyncio.ensure_future(coro)
    asyncio.get_event_loop().run_until_complete(fut)
    print(time.time()-t)
    print(fut.result())
    print()
