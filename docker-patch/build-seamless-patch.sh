cat seamless/docker-patch/Dockerfile | docker buildx build \
    --build-context seamless=seamless \
    --build-context seamless-tools=seamless-tools \
    -t rpbs/seamless:patch \
    --progress plain \
    -