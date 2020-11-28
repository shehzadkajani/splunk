from __future__ import absolute_import
from abc import abstractmethod
from rapid_diag.abstractstatic import abstractstatic


class ResourceUsageCollector(object):
    def __init__(self):
        self.lastIteration = None

    @abstractstatic
    def get_metric():
        pass

    @abstractmethod
    def get_target(self):
        pass

    @abstractmethod
    def get_current_usage(self):
        pass

    @abstractmethod
    def _update(self):
        pass

    # this is a trick so we can collect synchronized data on 2 metrics derived from the same source
    def update(self, iteration):
        try:
            if iteration == self.lastIteration:
                return True
        except AttributeError:
            pass
        self.lastIteration = iteration
        return self._update()
