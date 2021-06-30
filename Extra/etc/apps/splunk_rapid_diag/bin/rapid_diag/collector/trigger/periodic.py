# python imports
from __future__ import print_function, absolute_import
import os
import sys
import math
import datetime
import threading

# if collector is ran from CLI
SPLUNK_HOME = os.environ.get('SPLUNK_HOME')
SPLUNK_DB = os.environ.get('SPLUNK_DB')
if not SPLUNK_HOME or not SPLUNK_DB:
    print('ERROR: SPLUNK_HOME and SPLUNK_DB must be set in environment path.\nExecute the file via Splunk\'s python e.g $SPLUNK_HOME/bin/splunk cmd python <file_name.py>', file=sys.stderr)
    exit(1)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))))

# local imports
import logger_manager as log
from rapid_diag.collector.trigger.trigger import Trigger
from rapid_diag.collector.type import Type
from rapid_diag.collector.collector import Collector
from rapid_diag.collector.collector_result import CollectorResult, AggregatedCollectorResult
from rapid_diag.util import build_rapid_diag_timestamp
from rapid_diag.serializable import Serializable
from rapid_diag.session_globals import SessionGlobals
from rapid_diag.process_abstraction import ProcessLister


# global variables
_LOGGER = log.setup_logging("periodic")
IS_LINUX = sys.platform.startswith('linux')


class Periodic(Trigger, Serializable):
    def __init__(self, sampleCount, interval, collectors=None, state=Collector.State.WAITING):
        Trigger.__init__(self)
        self.collectors = collectors if collectors is not None else []
        self.sampleCount = int(sampleCount)
        self.interval = float(interval)
        self.state = state

    def _collect_impl(self, runContext):

        _LOGGER.info('Starting periodic collection with sample count=' + str(self.sampleCount) + ' interval=' + str(self.interval))
        _LOGGER.debug("Task assigned to thread: " + str(threading.current_thread().name))
        _LOGGER.debug("ID of process running task: "+str(os.getpid()))

        curContext = runContext.clone()
        self.promote_state(Collector.State.COLLECTING, curContext.stateChangeObservers)

        # coping(deepcopy) the collectors to another list
        # `self.filter_collector` removes the collectors with conflicting resources
        # coping into list to provide same collectors to every sample of periodic collection
        selected_collectors = [collector for collector in self.collectors]

        result = AggregatedCollectorResult()
        self.promote_state(Collector.State.COLLECTING, runContext.stateChangeObservers)
        for i in range(self.sampleCount):
            # creating deepcopy of selected_collectors
            self.collectors = [collector for collector in selected_collectors]
            numDigitsIdx = int(math.ceil(math.log10(self.sampleCount)))

            curContext.suffix = "_" + str(i).zfill(numDigitsIdx) + '_' + build_rapid_diag_timestamp()
            self.filter_collectors()

            tokens = []
            for collector in self.collectors:
                tokens.append(SessionGlobals.get_threadpool().add_task(collector.collect, curContext))

            for token in tokens:
                token.wait()
                result.addResult(token.get_result())

            if i != self.sampleCount - 1:
                if self.wait_for_state(Collector.State.ABORTED, self.interval) == Collector.State.ABORTING:
                    return CollectorResult.Aborted('Periodic collector aborted by user', _LOGGER)
        return result

    def getType(self):
        return Type.CONTINUOUS

    def __repr__(self):
        return "Periodic(Number of Samples: %r, Intervals: %r)" % (self.sampleCount, self.interval)

    def toJsonObj(self):
        return {
            'sampleCount': self.sampleCount,
            'interval': self.interval,
            'collectors': self.collectors,
            'state': Collector.State.get_status_string(self.state)
        }

    @staticmethod
    def validateJson(obj):
        data_types = {"sampleCount": (int,), "interval": (float, int), "collectors" : (list ,)}
        for field in list(filter(lambda x: x in obj.keys(), data_types.keys())):
            Serializable.check_data_type(obj[field], data_types[field], field)

        value_range = {"sampleCount": [1, Collector.MAX_CNT], "interval": [0.01, Collector.MAX_TIME]}
        for field in list(filter(lambda x: x in obj.keys(), value_range.keys())):
            Serializable.check_value_in_range(obj[field], value_range[field], field)

    @staticmethod
    def fromJsonObj(obj):
        return Periodic(obj['sampleCount'], obj['interval'], obj['collectors'], Collector.State.get_status_code(obj.get("state")))

Serializable.register(Periodic)
