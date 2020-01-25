from ipykernel.kernelapp import IPKernelApp
namespace = {"a": 1234}
app = IPKernelApp.instance(user_ns=namespace, connection_file="/tmp/seamless-1.json")
app.initialize()
app.start()