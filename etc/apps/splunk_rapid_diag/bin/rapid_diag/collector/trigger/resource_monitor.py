# python imports
from __future__ import print_function, absolute_import
import os
import sys
import time
import threading

# if collector is ran from CLI
SPLUNK_HOME = os.environ.get('SPLUNK_HOME')
SPLUNK_DB = os.environ.get('SPLUNK_DB')
if not SPLUNK_HOME or not SPLUNK_DB:
    print('ERROR: SPLUNK_HOME and SPLUNK_DB must be set in environment path.\nExecute the file via Splunk\'s python e.g $SPLUNK_HOME/bin/splunk cmd python <file_name.py>', file=sys.stderr)
    exit(1)
sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))))))

# local imports
import logger_manager as log
from rapid_diag.collector.trigger.trigger import Trigger
from rapid_diag.collector.trigger.resource_monitor_trackers import MovingAverageResourceMonitorTracker
from rapid_diag.collector.type import Type
from rapid_diag.collector.collector import Collector
from rapid_diag.collector.collector_result import CollectorResult, AggregatedCollectorResult
from rapid_diag.util import build_rapid_diag_timestamp
from rapid_diag.serializable import Serializable
from rapid_diag.session_globals import SessionGlobals
from rapid_diag.process_abstraction import ProcessLister

_LOGGER = log.setup_logging("resource_monitor")
IS_LINUX = sys.platform.startswith('linux')


class ResourceMonitor(Trigger, Serializable):
    def __init__(self, resource_monitor_trackers, collectors=None, state=Collector.State.WAITING, sleep_time=5):
        Trigger.__init__(self)
        self.resource_monitor_trackers = resource_monitor_trackers
        self.state = state
        self.collectors = collectors if collectors is not None else []
        self.sleep_time = sleep_time

    def _collect_impl(self, runContext):
        _LOGGER.info('Starting resource monitor collection with resource monitor trackers=' + str(self.resource_monitor_trackers))
        _LOGGER.debug("Task assigned to thread: " + str(threading.current_thread().name))
        _LOGGER.debug("ID of process running task: "+str(os.getpid()))
        curContext = runContext.clone()
        curContext.suffix = '_' + build_rapid_diag_timestamp()
        try:
            iteration = 0
            while self.get_state() != Collector.State.ABORTING:
                iteration += 1
                for tracker in self.resource_monitor_trackers:
                    tracker.update(iteration)
                    if tracker.has_crossed_threshold():
                        _LOGGER.info('Crossed the threshold with monitor trackers=' + str(self.resource_monitor_trackers))
                        self.promote_state(Collector.State.COLLECTING, curContext.stateChangeObservers)
                        return self._collect(curContext)
                time.sleep(self.sleep_time)
        except Exception as e:
            return CollectorResult.Exception(e, 'Error running resource monitor trigger', _LOGGER)
        finally:
            if self.get_state() == Collector.State.ABORTING:
                return CollectorResult.Aborted('Resource Monitor trigger aborted by user', _LOGGER)

    def _collect(self, runContext):

        # filtering out the collectors whose resources are not available
        self.filter_collectors()

        result = AggregatedCollectorResult()
        # start collection
        tokens = []
        for collector in self.collectors:
            tokens.append(SessionGlobals.get_threadpool().add_task(collector.collect, runContext))
        for token in tokens:
            token.wait()
            result.addResult(token.get_result())
        return CollectorResult.Failure("All resources are occupied, could not start any of the collectors.") if (not self.collectors) and self.conflicts\
            else result

    def getType(self):
        return Type.CONTINUOUS

    def __repr__(self):
        tracekrs = ""
        for tracker in self.resource_monitor_trackers:
            tracekrs += str(tracker)
        return "ResourceMonitor(Tracker(s): " + tracekrs + ")"

    def toJsonObj(self):
        return {
            "resource_monitor_trackers": self.resource_monitor_trackers,
            "collectors": self.collectors,
            "state": Collector.State.get_status_string(self.state)
        }

    @staticmethod
    def validateJson(obj):
        data_types = {"resource_monitor_trackers": (list,), "collectors": (list,)}
        for field in list(filter(lambda x: x in obj.keys(), data_types.keys())):
            Serializable.check_data_type(obj[field], data_types[field], field)

    @staticmethod
    def fromJsonObj(obj):
        return ResourceMonitor(obj['resource_monitor_trackers'], obj['collectors'], Collector.State.get_status_code(obj.get("state")))


Serializable.register(ResourceMonitor)
