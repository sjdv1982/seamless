# Docker images below do not contain a Fortran compiler
# The module is compiled remotely, then sent back, imported and executed
# invoke compile-fortran-build-module-remote-peer1.sh, and wait a few seconds

# Seamless Docker image
docker run --rm --network host -v `pwd`:/script seamless python3 /script/compile-fortran-build-module-remote.py

# or: Seamless-devel docker image
###seamlessdir=$(python3 -c 'import seamless, os; print(os.path.split(seamless.__file__)[0])')
###echo $seamlessdir
###docker run --rm --network host -v `pwd`:/script -v $seamlessdir:/seamless -e PYTHONPATH=/ seamless-devel python3 /script/compile-fortran-build-module-remote.py
