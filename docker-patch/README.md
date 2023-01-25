This directory is meant to patch the rpbs/seamless Docker image into a new bugfix release (e.g. from 0.10 to 0.10.2) by just replacing a few files, rather than re-building everything.

Instructions: edit the Dockerfile. After each new normal release, remove all COPY/RUN statements.

- In the same directory, git clone both the seamless and seamless-tools repos.
- Run ./seamless/docker-patch/build-seamless-patch.sh
- Docker tag rpbs/seamless:patch to e.g. rpbs/seamless:latest