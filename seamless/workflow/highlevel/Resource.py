import os


class Resource:
    """Helper class to facilitate mounting. On assign, Seamless will mount "filename" """

    def __init__(self, filename, data=None):
        self.filename = filename
        if data is None and os.path.exists(filename):
            with open(filename) as f:
                data = f.read()
        self.data = data
