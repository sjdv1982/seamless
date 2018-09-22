class Resource:
    """Helper class to facilitate mounting. On assign, Seamless will mount "filename" """
    def __init__(self, filename, data):
        self.filename = filename
        self.data = data
