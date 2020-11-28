# python imports
from __future__ import absolute_import

# local imports
import logger_manager as log
from rapid_diag.collector.collector import Collector
from rapid_diag.collector.collector_result import CollectorResult



_LOGGER = log.setup_logging("trigger")


class Trigger(Collector):
    def __init__(self):
        Collector.__init__(self)
        self.conflicts = False

    def add(self, collector):
        self.collectors.append(collector)

    def remove(self, collector):
        try:
            index = self.collectors.index(collector)
            self.collectors = self.collectors[:index] + self.collectors[index+1:]
        except ValueError:
            return False
        return True

    def apply_to_self(self, functor, depth=0):
        Collector.apply_to_self(self, functor, depth)
        for collector in self.collectors:
            collector.apply_to_self(functor, depth + 1)

    def get_required_resources(self):
        resources = []
        for collector in self.collectors:
            resources.extend(collector.get_required_resources())
        return resources

    def _filter_collectors_helper(self, conflicting_resources):
        for i in reversed(range(len(self.collectors))):
            collector = self.collectors[i]
            if isinstance(collector, Trigger):
                collector._filter_collectors_helper(conflicting_resources)
            elif set(collector.get_required_resources()).intersection(conflicting_resources):
                self.conflicts = True
                del self.collectors[i]

    def filter_collectors(self):
        import rapid_diag.collector.resource_manager
        resource_manager_mod = lambda: rapid_diag.collector.resource_manager
        resource_manager = resource_manager_mod().ResourceManager(self.collectors)

        if not resource_manager.should_start_task():
            _LOGGER.debug("Resources conflicting with the trigger are " + " ".join(([str(cr) for cr in resource_manager.conflicting_resources])))
            self._filter_collectors_helper(resource_manager.conflicting_resources)
