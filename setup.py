# Always prefer setuptools over distutils
from setuptools import setup, find_packages
from os import path

setup(
    name='seamless-framework',

    version='0.2',

    description='a cell-based programming framework',

    long_description="""Seamless is a framework to set up computations (and visualizations) that respond to changes in cells. Cells contain the input data as well as the source code of the computations, and all cells can be edited interactively.""",

    url='https://github.com/sjdv1982/seamless',

    author='Sjoerd de Vries',
    author_email='sjdv1982@gmail.com',

    license='MIT',

    classifiers=[
        'Development Status :: 3 - Alpha',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'Topic :: Scientific/Engineering :: Visualization',
        'Topic :: Software Development',
        'Topic :: Software Development :: Object Brokering',
        'Topic :: Software Development :: User Interfaces',
        'Topic :: System',
        'Framework :: IPython',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: MIT License',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],

    keywords='framework interactive interoperability reproducible-science protocol incremental-computation distributed-computing'
    packages=find_packages(),

    install_requires=[
      'ipython', 'numpy', 'cson', 'websockets', 'tornado', 'requests',
      'aiohttp', 'aiohttp_cors', 'wurlitzer', 'docker'
    ],

    extras_require={
        'recommended': ['scipy', 'pandas', 'cython', 'pyqt5'],
    },

    python_requires='>=3.5',
)
