from __future__ import absolute_import
from rapid_diag.collector.trigger.resource_usage_metrics import SystemwideCpuUsageCollector, SystemwideMemory, SystemwidePhysicalMemoryUsageCollector, SystemwideVirtualMemoryUsageCollector


class ResourceUsageCollectorFactory(object):
    def _systemwide_memory(self):
        try:
            return self.systemwide_memory
        except AttributeError:
            self.systemwide_memory = SystemwideMemory()
        return self.systemwide_memory

    buildmap = {
        'system': {
            SystemwideCpuUsageCollector.get_metric(): lambda self: SystemwideCpuUsageCollector(),
            SystemwidePhysicalMemoryUsageCollector.get_metric(): lambda self: SystemwidePhysicalMemoryUsageCollector(self._systemwide_memory()),
            SystemwideVirtualMemoryUsageCollector.get_metric(): lambda self: SystemwideVirtualMemoryUsageCollector(self._systemwide_memory())
        }
    }

    def build(self, target, metric):
        if target != 'system':
            raise TypeError('Invalid target ' + str(target))
        if metric not in ResourceUsageCollectorFactory.buildmap[target]:
            raise TypeError('Invalid metric ' + str(metric) + ' for target ' + str(target))
        return ResourceUsageCollectorFactory.buildmap[target][metric](self)
