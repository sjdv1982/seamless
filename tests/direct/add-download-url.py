from io import StringIO
import urllib.request
from hashlib import sha3_256
import numpy as np
from seamless import Checksum, CacheMissError
from seamless.config import add_download_urls

import seamless

seamless.delegate(False)

iris_url = "https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/sklearn/datasets/data/iris.csv"

with urllib.request.urlopen(iris_url) as f:
    iris_data = f.read()

cs = sha3_256(iris_data).hexdigest()
print("Iris data set checksum:", cs)

checksum = Checksum(cs)
print("Find...")
url_info = checksum.find(verbose=True)
print("...", url_info)
try:
    downloaded_iris_data = checksum.resolve(celltype="text")
except CacheMissError:
    print("Initial try: cache miss...")

add_download_urls(
    {
        cs: iris_url,
    }
)

print("Find...")
url_info = checksum.find(verbose=True)
print("...", url_info)

downloaded_iris_data = checksum.resolve(celltype="text")
print("Download successful")
print(downloaded_iris_data.splitlines()[0])
arr = np.genfromtxt(
    StringIO(downloaded_iris_data), delimiter=",", dtype=None, encoding=None
)
print(arr[0])
