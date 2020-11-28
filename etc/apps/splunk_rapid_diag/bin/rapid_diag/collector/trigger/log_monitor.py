# python imports
from __future__ import print_function, absolute_import
import os
import sys
import time
import datetime
import re
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
from splunklib import six
import logger_manager as log
from rapid_diag.collector.trigger.trigger import Trigger
from rapid_diag.collector.trigger.monitored_file import MonitoredFile
from rapid_diag.collector.type import Type
from rapid_diag.collector.collector import Collector
from rapid_diag.collector.collector_result import CollectorResult, AggregatedCollectorResult
from rapid_diag.util import get_splunkhome_path, build_rapid_diag_timestamp
from rapid_diag.serializable import Serializable
from rapid_diag.session_globals import SessionGlobals
from rapid_diag.process_abstraction import ProcessLister

_LOGGER = log.setup_logging("log_monitor")
MAX_RETRIES = 10
IS_LINUX = sys.platform.startswith('linux')


class LogMonitor(Trigger, Serializable):
    def __init__(self, selectedFile, regex, collectors=None, state=Collector.State.WAITING):
        Trigger.__init__(self)
        self.selectedFile = selectedFile
        self.regex = regex
        self.collectors = collectors if collectors is not None else []
        self.state = state

    def _collect_impl(self, runContext):

        _LOGGER.info('Starting log monitor collection with log file=' + str(self.selectedFile) + ' regex=' + str(self.regex))
        _LOGGER.debug("Task assigned to thread: " + str(threading.current_thread().name))
        _LOGGER.debug("ID of process running task: "+str(os.getpid()))
        
        # This while loop takes care of IOError when the log file is just renamed and new file is not created
        retries = MAX_RETRIES
        log_file_path = get_splunkhome_path(["var", "log", "splunk", self.selectedFile])
        curContext = runContext.clone()
        curContext.suffix = '_' + build_rapid_diag_timestamp()
        while retries > 0:
            try:
                with MonitoredFile(log_file_path) as file:
                    while self.get_state() != Collector.State.ABORTING:
                        line = file.readline()
                        retries = MAX_RETRIES
                        if not line:
                            time.sleep(0.1)
                        # Ignore the logged line by rapid_diag rest call
                        # Note: log monitor should not get triggered on log of 
                        # our app's rest call.
                        elif "/rapid_diag/" in line:
                            pass
                        elif re.search(self.regex, line):
                            _LOGGER.info('Regex matched with log file=' + str(self.selectedFile) + ' regex=' + str(self.regex))
                            self.promote_state(Collector.State.COLLECTING, curContext.stateChangeObservers)
                            return self._collect(curContext)
            except IOError:
                retries -= 1
                if retries == 0:
                    return CollectorResult.Failure('Couldn\'t find the file ' + str(log_file_path), _LOGGER)
                time.sleep(0.2)
            except Exception as e:
                return CollectorResult.Exception(e, 'Error running log monitor trigger', _LOGGER)
            finally:
                # returning if aborted between retries
                if self.get_state() == Collector.State.ABORTING:
                    return CollectorResult.Aborted('Log Monitor trigger aborted by user', _LOGGER)


    def _collect(self, runContext):

        # filtering out the collectors whose resources are not available
        self.filter_collectors()

        result = AggregatedCollectorResult()
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
        return "Log Monitor(Selected file: %s, Regex: %s)" % (self.selectedFile, self.regex)

    def toJsonObj(self):
        return {
            'selectedFile': self.selectedFile,
            'regex': self.regex,
            'collectors': self.collectors,
            'state': Collector.State.get_status_string(self.state)
        }

    @staticmethod
    def validateJson(obj):
        data_types = {"selectedFile": (six.text_type,), "regex": (six.text_type,), "collectors": (list,)}
        for field in list(filter(lambda x: x in obj.keys(), data_types.keys())):
            Serializable.check_data_type(obj[field], data_types[field], field)

        string_value = ["selectedFile"]
        for field in list(filter(lambda x: x in obj.keys(), string_value)):
            Serializable.check_string_value(obj[field], field)

    @staticmethod
    def fromJsonObj(obj):
        return LogMonitor(obj['selectedFile'], obj['regex'], obj['collectors'], Collector.State.get_status_code(obj.get("state")))


Serializable.register(LogMonitor)
