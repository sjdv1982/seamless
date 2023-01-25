# syntax=docker/dockerfile:1

FROM rpbs/seamless:0.10
USER root
RUN --mount=from=seamless cp seamless/communion_client.py seamless/communion_server.py /opt/conda/lib/python3.8/site-packages/seamless && \
    cp seamless/core/transformation.py /opt/conda/lib/python3.8/site-packages/seamless/core/transformation.py && \
    cp seamless/highlevel/assign.py  /opt/conda/lib/python3.8/site-packages/seamless/highlevel/assign.py
COPY --from=seamless-tools scripts/serve-graph.py /home/jovyan/seamless-scripts

