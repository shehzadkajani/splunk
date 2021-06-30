# this is a release version - we do not profile those :)

class Profiler(object):
    def __init__(self, logger):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

