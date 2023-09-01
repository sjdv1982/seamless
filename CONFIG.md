# Seamless configuration document

## Delegated mode vs embedded mode

You can run Seamless in *delegated* or *embedded* mode. Embedded mode does its own calculation and buffer management.

### How to set up delegation

*Delegated* mode is activated using `seamless.config.delegate(...)`.  This will block local execution and then contact a Seamless assistant via the communion protocol, which will provide a Seamless database URL and buffer config (buffer read folder, buffer read server, buffer write server). There is also a dummy assistant `seamless-jobslave`, which will provide an empty config. This will cause the database + buffer config to be read from environment variables.
The easiest way to set it all up in a local/dummy config:
```
seamless-database
seamless-hashserver (alias to docker compose up ...)
seamless-jobslave
seamless-ipython => import seamless; seamless.delegate()
```

But the "real" config is of course using a real Seamless assistant which can send jobs to a HPC cluster, the cloud, etc.

There are also "manual" commands to set up delegation:

```
seamless.config.block_local()
seamless.config.communion_server.start()  # read from env
seamless.config.database.connect()   # read from env
seamless.config.add_buffer_folder / .add_buffer_read_server / .set_buffer_write_server
```

### Requirements for delegation and embedding

Once delegation has been set up, Seamless should run anywhere, even under Windows.

As for embedded mode, Seamless inside the Docker container always supports it. Seamless outside the Docker container needs the Seamless conda environment and its packages (some e.g. matplotlib and snakemake are optional). *In addition, Seamless in embedded mode needs to support os.fork(), i.e. Linux/Unix*. Also, embedded buffers and calculations can claim a lot of CPU/memory resources. Finally, embedded Seamless does not really support environments, other that manual installation of conda/pip packages inside the Seamless Docker container or conda environment.

## Seamless syntax styles

TODO: Make something like "seamless.embedded_mode()" or "seamless.config.delegate(False)" obligatory? Or give a warning when you didn't do it?

Bash syntax requires delegated mode. All other syntaxes work in either mode, but embedded mode requires more dependencies and does not run under Windows (only Docker).
- Bash syntax (bash script, delegated mode). TODO: describe "file.ext.TRANSFORMATION"
- Functional syntax (decorator "@transformer", Python script)
Functional syntax *will* work under Jupyter, but there is a performance hit (thread)
- Coroutine syntax (decorator "@async_transformer", Jupyter notebook)
- Object-oriented syntax (bash or Python code. Use seamless.highlevel classes without Context. mounting supported, attributes can be bound. Transformation object, to be queried or used in another Transformer)
- Workflow mode. Polyglot, inside and outside (throw-away) code. Can be delegated or embedded. In delegated mode, transformer code can be nested as it may contain functional syntax. State of the workflow can be saved in a file. Workflow buffers can be exported as a vault or zip. Reactive evaluation. Building web servers is easy. If statements are hard. Windows support not certain.