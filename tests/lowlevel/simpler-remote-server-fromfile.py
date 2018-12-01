with open("simpler-remote.rqseamless", "rb") as f:
    rqdata = f.read()

from seamless.core.asynckernel.remote import decode, encode
from seamless.core.asynckernel.remote.server.job_transformer import transform_job

transformer_params, output_signature, values, access_modes, content_types = decode(rqdata)
print(transformer_params)
print(values)
print(access_modes)
print(content_types)

rqdata2 = encode(transformer_params, output_signature, values, access_modes, content_types)
print(rqdata == rqdata2)

result = transform_job(rqdata)
print(result)
#TODO: encode as RPSEAMLESS?
