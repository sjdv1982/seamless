# syntax=docker/dockerfile:1

FROM rpbs/seamless:0.13
USER root
RUN --mount=from=seamless cat docker-patch/filelist | xargs -I {} dirname {} | xargs -I {} mkdir -p /usr/local/src/seamless/{}
RUN --mount=from=seamless cat docker-patch/filelist | xargs -I {} cp {} /usr/local/src/seamless/{}
