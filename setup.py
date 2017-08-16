from distutils.core import setup

setup(
    name='seamless-framework',
    version='0.1',
    packages=['seamless', 'seamless.gui', 'seamless.lib', 'seamless.lib.gui', 'seamless.lib.gui.gl', 'seamless.lib.ngl',
              'seamless.lib.plotly', 'seamless.core', 'seamless.core.pysynckernel', 'seamless.core.pythreadkernel',
              'seamless.silk', 'seamless.silk.classes', 'seamless.silk.registers', 'seamless.silk.transform',
              'seamless.silk.typeparse', 'seamless.silk.typeparse.macros', 'seamless.slash', 'seamless.dtypes',
              'seamless.dtypes.gl', 'seamless.dtypes.gl.gloo', 'seamless.dtypes.gl.color'],
    url='http://sjdv1982.github.io/seamless',
    license='MIT',
    author='Sjoerd de Vries',
    install_requires=['pandas', 'websockets', 'PyQt5', 'cson', 'numpy', 'PyOpenG', 'IPython'],
    author_email='',
    description='A framework to set up computations (and visualizations) that respond to changes in cells. Cells contain the input data as well as the source code of the computations, and all cells can be edited live.',
    entry_points={'console_scripts': ['seamless=seamless.tools.seamless:main',]
                  }
)
