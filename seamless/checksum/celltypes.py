"""Celltypes enumeration"""

celltypes = [
    "binary",
    "mixed",
    "text",
    "python",
    "ipython",
    "plain",
    "cson",
    "yaml",
    "str",
    "bytes",
    "int",
    "float",
    "bool",
    "checksum",
]

celltypes2 = celltypes + ["silk"]

text_types = (
    "text",
    "python",
    "ipython",
    "cson",
    "yaml",
    "str",
    "int",
    "float",
    "bool",
)

text_types2 = (
    "text",
    "python",
    "ipython",
    "cson",
    "yaml",
    "silk",  # alias for "mixed"
)
