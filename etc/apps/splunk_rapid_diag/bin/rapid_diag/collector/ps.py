# python imports
from __future__ import print_function, absolute_import
import os
import re
import sys
import threading
import tempfile
import shutil

# if colllector is ran from CLI
SPLUNK_HOME = os.environ.get('SPLUNK_HOME')
SPLUNK_DB = os.environ.get('SPLUNK_DB')
if not SPLUNK_HOME or not SPLUNK_DB:
    print('ERROR: SPLUNK_HOME and SPLUNK_DB must be set in environment path.\nExecute the file via Splunk\'s python e.g $SPLUNK_HOME/bin/splunk cmd python <file_name.py>', file=sys.stderr)
    exit(1)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))


# local imports
import logger_manager as log
from rapid_diag.collector.type import Type
from rapid_diag.collector.resource import Resource
from rapid_diag.collector.collector import Collector
from rapid_diag.collector.tools_collector import ToolsCollector
from rapid_diag.collector.collector_result import CollectorResult
from rapid_diag.collector.tool_manager import ToolAvailabilityManager
from rapid_diag.util import build_rapid_diag_timestamp
from rapid_diag.serializable import Serializable
from rapid_diag.session_globals import SessionGlobals

_LOGGER = log.setup_logging("ps")
IS_LINUX = sys.platform.startswith('linux')

REX_STDERR_NOT_LOGGABLE_LINE = re.compile('no matching address range')
REX_STDOUT_MAIN = re.compile('(?i)thread.*main')
REX_SYS_PROC_NOT_SUPPORTED = re.compile('System process is not supported')


class PS(Collector, ToolsCollector, Serializable):
    """ RapidDiag collector allows collecting Report of current running process """

    def __init__(self, state=Collector.State.WAITING):
        Collector.__init__(self)
        ToolsCollector.__init__(self, valid_return_code=[0, None])
        self.tool_name = self.get_tool_name()
        self.state = state
        self.tool_manager_output = ToolAvailabilityManager.find(self.tool_name)

    @staticmethod
    def get_tool_name():
        return ("ps" if IS_LINUX else "tasklist.exe")

    @staticmethod
    def tool_missing():
        utility_name = PS.get_tool_name()
        tool_manager = SessionGlobals.get_tool_availability_manager()
        is_avail = tool_manager.is_available(utility_name)
        if is_avail:
            return None

        tempDir = tempfile.mkdtemp()
        try:
            dummy_obj = PS()
            _ = dummy_obj.collect(Collector.RunContext(tempDir, '', None))
            message = tool_manager.get_tool_message(utility_name)
            message = None if message == True else message
        finally:
            shutil.rmtree(tempDir, True)
        return message

    def getType(self):
        return Type.SNAPSHOT

    def get_required_resources(self):
        if not IS_LINUX:
            return [Resource('tasklist')]
        return [Resource('ps')]

    def toJsonObj(self):
        return {
            'state': Collector.State.get_status_string(self.state)
        }

    @staticmethod
    def validateJson(obj):
        pass

    @staticmethod
    def fromJsonObj(obj):
        return PS(Collector.State.get_status_code(obj.get("state")))

    def __repr__(self):
        return "PS"

    def _collect_impl(self, runContext):
        tool_manager = SessionGlobals.get_tool_availability_manager()
        if self.tool_manager_output.error_message is not None:
            status = CollectorResult.Failure(self.tool_manager_output.error_message, _LOGGER)
        else:
            self.promote_state(Collector.State.COLLECTING, runContext.stateChangeObservers)
            collectFun = self._collect_linux if IS_LINUX else self._collect_windows
            status = collectFun(runContext.outputDir, runContext.suffix)
        tool_worked = status.isSuccess() or self.get_state() == Collector.State.ABORTING
        tool_manager.set_available(self.tool_name, True if tool_worked else self.tool_manager_output.error_message)
        return status

    def _collect_windows(self, outputDir, suffix):
        """ For windows, collect Report of current running processes using tasklist utility."""
        _LOGGER.info('Starting ps collector using tasklist with' + ' outputDir=' + outputDir + ' suffix=' + suffix)
        _LOGGER.debug("Task assigned to thread: " + str(threading.current_thread().name))
        _LOGGER.debug("ID of process running task: "+str(os.getpid()))

        fname = os.path.join(outputDir, 'ps' + suffix)

        command = [self.tool_manager_output.toolpath, '/V', '/FO', 'CSV']
        _LOGGER.info('Collecting '+ ' '.join(command) + ' into ' + outputDir + ' suffix ' + suffix)

        with open(fname + ".csv", "a+") as output, open(fname + ".err", "a+") as error:
            try:
                result = self.run(command, output, error)
            except EnvironmentError as e:
                return CollectorResult.Exception(e, 'Error collecting ' + str(self.tool_name) +
                                                ', please confirm you have the ' + str(self.tool_name) + ' package ' +
                                                'installed in your system and that the ' + str(self.tool_name) +
                                                ' command is available -- path=' + os.getenv('PATH'), _LOGGER)
            except Exception as e:
                return CollectorResult.Exception(e, 'Error collecting ' + str(self.tool_name), _LOGGER)

        return result

    def _collect_linux(self, outputDir, suffix):
        """For Linux, collect Report of current running processes using tasklist utility."""
        _LOGGER.info('Starting ps collector using ps with' + ' outputDir=' + outputDir + ' suffix=' + suffix)
        _LOGGER.debug("Task assigned to thread: " +
                      str(threading.current_thread().name))
        _LOGGER.debug("ID of process running task: "+str(os.getpid()))

        command = [self.tool_manager_output.toolpath, 'aux', '-ejL']

        fname = os.path.join(outputDir, 'ps' + suffix)

        with open(fname + ".csv", "a+") as output, open(fname + ".err", "a+") as error:
            try:
                result = self.run(command, output, error)
            except EnvironmentError as e:
                return CollectorResult.Exception(e, 'Error collecting ' + str(self.tool_name) +
                                                ', please confirm you have the ' + str(self.tool_name) + ' package ' +
                                                'installed in your system and that the ' + str(self.tool_name) +
                                                ' command is available -- path=' + os.getenv('PATH'), _LOGGER)
            except Exception as e:
                return CollectorResult.Exception(e, 'Error collecting ' + str(self.tool_name), _LOGGER)

        return result


Serializable.register(PS)
