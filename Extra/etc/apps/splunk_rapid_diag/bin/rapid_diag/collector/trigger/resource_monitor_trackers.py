# python imports
from __future__ import absolute_import
from collections import deque
from abc import abstractmethod
from splunklib import six

# local imports
import logger_manager as log
from rapid_diag.collector.trigger.resource_usage_collector_factory import ResourceUsageCollectorFactory
from rapid_diag.serializable import Serializable

_LOGGER = log.setup_logging("resource_monitor_trackers")
MAX_THRESHOLD = 1e9


class ResourceMonitorTracker(object):
    @abstractmethod
    def update(self, iteration):
        pass

    @abstractmethod
    def has_crossed_threshold(self):
        pass


class MovingAverageResourceMonitorTracker(ResourceMonitorTracker, Serializable):
    resource_factory = ResourceUsageCollectorFactory()
    def __init__(self, resource_usage_collector, threshold, num_samples, invert):
        self.resource_usage_collector = resource_usage_collector
        self.threshold = float(threshold)
        self.num_samples = num_samples
        self.invert = -1 if invert in [True, -1] else 1
        self.samples = deque(maxlen=num_samples)
        self.sum = 0.

    def update(self, iteration):
        self.resource_usage_collector.update(iteration)
        sample = self.resource_usage_collector.get_current_usage()

        _LOGGER.debug("Metric: " + str(self.resource_usage_collector.get_metric()) + " Target: " + str(self.resource_usage_collector.get_target()) + " Iteration: " + str(iteration) + " Sample: " + str(sample))

        if len(self.samples) == self.num_samples:
            self.sum -= float(self.samples[0])

        self.samples.append(sample)
        self.sum += float(sample)

    def has_crossed_threshold(self):
        if len(self.samples) == self.num_samples:
            return self.invert*self.sum/self.num_samples > self.invert*self.threshold*(1 if self.resource_usage_collector.get_metric() == 'cpu' else 1024)
        return False

    def __repr__(self):
        return "(Metric: %s, Threshold: %r, Invert: %r)" % (self.resource_usage_collector, self.threshold, False if self.invert == 1 else True)

    def toJsonObj(self):
        return {
            'target': self.resource_usage_collector.get_target(),
            'metric': self.resource_usage_collector.__class__.get_metric(),
            'threshold': self.threshold,
            'num_samples': self.num_samples,
            'invert': True if self.invert == -1 else False
        }

    @staticmethod
    def check_threshold_in_range(value, field_range, key, metric):
        threshold_range = field_range
        if metric == "cpu":
            threshold_range = [0, 100]
        if not threshold_range[0] < value <= threshold_range[1]:
            raise ValueError(str(key) + "(" + metric + ") " + ": value should be greater than " + str(threshold_range[0]) + " and at most " + str(threshold_range[1]) + ".")

    @staticmethod
    def validateJson(obj):
        data_types = {"target": (six.text_type,), "metric": (six.text_type,), "threshold" : (float,int), "num_samples" : (int,), "invert" : (bool,)}
        for field in list(filter(lambda x: x in obj.keys(), data_types.keys())):
            Serializable.check_data_type(obj[field], data_types[field], field)

        value_range = {"threshold": [0, MAX_THRESHOLD]}
        for field in list(filter(lambda x: x in obj.keys(), value_range.keys())):
            MovingAverageResourceMonitorTracker.check_threshold_in_range(obj[field], value_range[field], field, obj["metric"])

        string_value = ["target", "metric"]
        for field in list(filter(lambda x: x in obj.keys(), string_value)):
            Serializable.check_string_value(obj[field], field)

        if obj.get('target') not in ResourceUsageCollectorFactory.buildmap:
            raise ValueError("target: Value should be " + ' , or '.join(ResourceUsageCollectorFactory.buildmap.keys()))
        if obj.get('metric') not in ResourceUsageCollectorFactory.buildmap[obj.get('target')]:
            raise TypeError("metric: Value should be " + ', or '.join(ResourceUsageCollectorFactory.buildmap[obj.get('target')].keys()))
        if obj.get('num_samples') != 10:
            raise ValueError("num_samples: Value should be 10.")

    @staticmethod
    def fromJsonObj(obj):
        return MovingAverageResourceMonitorTracker(MovingAverageResourceMonitorTracker.resource_factory.build(obj['target'], obj['metric']), obj['threshold'], obj['num_samples'], obj['invert'])

Serializable.register(MovingAverageResourceMonitorTracker)
