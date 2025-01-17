Run as: ./run.sh > run.out 2>&1

Must be run in an environment where:
 aiofiles is installed, SEAMLESS_TOOLS_DIR is defined, and seamless-fairdir-XXXX / seamless-bufferdir-XXXX are available

All four Seamless environments ((docker OR conda) + (standard OR devel)) can execute this, as long as SEAMLESS_TOOLS_DIR is defined,
which by default is only the case for conda + devel.