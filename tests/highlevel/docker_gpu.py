from seamless.highlevel import Context, Transformer

#docker run --rm --gpus all --shm-size 1gb nvidia/cuda:11.0-base \
# bash -c 'nvidia-smi && df /dev/shm'

ctx = Context()

docker_options = {
    "shm_size":"1gb",
    "device_requests":[
        {"count":-1, "capabilities":[['gpu']]}
    ]
}

tf = ctx.tf = Transformer()
tf.language = "bash"
tf.environment.set_docker(
    {
        "name": "nvidia/cuda:11.0-base",
        "options": docker_options,
    }
)

tf.code = "nvidia-smi && df /dev/shm"
ctx.compute()
print(tf.exception)