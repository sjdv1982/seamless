from setuptools import setup, find_packages

setup(
    name="seamless",
    # version='', # disabled for conda
    url="https://github.com/sjdv1982/seamless.git",
    author="Sjoerd de Vries",
    author_email="sjdv1982@gmail.com",
    description="Seamless is a framework to set up protocols (workflows) and computations that respond to changes in cells. Cells define the input data as well as the source code of the computations, and all cells can be edited interactively.",
    packages=find_packages(),
    package_data={
        "": [
            "checksum/mime.types",
            "js/*.*",
            "compiler/*.cson",
            "workflow/graphs/*.seamless",
            "workflow/graphs/*.zip",
            "workflow/stdlib/*.seamless",
            "workflow/stdlib/*.zip",
            "workflow/webunits/*.yaml",
        ],
    },
    zip_safe=False,
    # install_requires=[...], # disabled for conda
)
