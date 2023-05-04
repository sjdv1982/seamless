# syntax=docker/dockerfile:1

FROM rpbs/seamless:0.11
USER root
RUN apt update && apt install less gcc g++ gfortran -y
RUN sed -i 's/3.10.9/3.10.*/' /opt/conda/conda-meta/pinned
RUN --mount=from=seamless cat docker-patch/filelist | xargs -I {} dirname {} | xargs -I {} mkdir -p /opt/conda/lib/python3.10/site-packages/{}
RUN --mount=from=seamless cat docker-patch/filelist | xargs -I {} cp {} /opt/conda/lib/python3.10/site-packages/{}
#COPY --from=seamless-tools scripts/serve-graph.py /home/jovyan/seamless-scripts
USER jovyan
COPY --from=seamless tests/highlevel/debugmount/pypackage /home/jovyan/seamless-tests/highlevel/debugmount/pypackage
RUN --mount=from=seamless,target=/TEMP cat /TEMP/docker-patch/filelist-test | xargs -t -I {} cp /TEMP/tests/{} /home/jovyan/seamless-tests/{}
