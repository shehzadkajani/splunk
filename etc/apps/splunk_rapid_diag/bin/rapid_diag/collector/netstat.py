from __future__ import print_function, absolute_import
import sys
import os
import threading
import tempfile
import shutil

# if collector is ran from CLI
SPLUNK_HOME = os.environ.get("SPLUNK_HOME")
SPLUNK_DB = os.environ.get("SPLUNK_DB")
if not SPLUNK_HOME or not SPLUNK_DB:
    print("ERROR: SPLUNK_HOME and SPLUNK_DB must be set in environment path.\nExecute the file via Splunk's python e.g $SPLUNK_HOME/bin/splunk cmd python <file_name.py>", file=sys.stderr)
    exit(1)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))

# local imports
import logger_manager as log
from rapid_diag.collector.type import Type
from rapid_diag.collector.resource import Resource
from rapid_diag.collector.collector import Collector
from rapid_diag.collector.tools_collector import ToolsCollector
from rapid_diag.collector.collector_result import CollectorResult, AggregatedCollectorResult
from rapid_diag.collector.tool_manager import ToolAvailabilityManager
from rapid_diag.util import build_rapid_diag_timestamp
from rapid_diag.serializable import Serializable
from rapid_diag.session_globals import SessionGlobals

_LOGGER = log.setup_logging("netstat")
IS_LINUX = sys.platform.startswith('linux')

class NetStat(Collector, ToolsCollector, Serializable):
    """RapidDiag Collector  gathers network statistics and network connections"""

    def __init__(self, state=Collector.State.WAITING):
        Collector.__init__(self)
        ToolsCollector.__init__(self)
        self.state = state
        self.tool_name = self.get_tool_name()
        self.tool_manager_output = ToolAvailabilityManager.find(self.tool_name)

    @staticmethod
    def get_tool_name():
        return ("netstat" if IS_LINUX else "netstat.exe")

    @staticmethod
    def tool_missing():
        utility_name = NetStat.get_tool_name()
        tool_manager = SessionGlobals.get_tool_availability_manager()
        is_avail = tool_manager.is_available(utility_name)
        if is_avail == True:
            return None
        tempDir = tempfile.mkdtemp()
        try:
            dummy_obj = NetStat()
            _ = dummy_obj.collect(Collector.RunContext(tempDir, "", None))
            message = tool_manager.get_tool_message(utility_name)
            message = None if message == True else message
        finally:
            shutil.rmtree(tempDir, True)
        return message

    def getType(self):
        return Type.SNAPSHOT

    def get_required_resources(self):
        return [Resource('netstat')]

    def __repr__(self):
        return "Netstat"

    def toJsonObj(self):
        return {'state': Collector.State.get_status_string(self.state)}

    @staticmethod
    def validateJson(obj):
        pass

    @staticmethod
    def fromJsonObj(obj):
        return NetStat(Collector.State.get_status_code(obj.get("state")))

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

    def _collect_linux(self, outputDir, suffix):
        """Collects network statistics and current network connections in Windows.
        `netstat` is required to run this collection.
        Collector gathers data and stores output in `.out` file and errors in `.err` file

        Parameters
        ----------
        outputDir : string
            Data collection directory path
        suffix : string
            Suffix to the file

        Returns
        -------
        CollectorResult
            CollectorResult.Success() if successful
            OR CollectorResult.Failure() if failure
            OR CollectorResult.Exception() otherwise
        """

        _LOGGER.info("Starting Netstat collector with: outputDir='" + outputDir + "' suffix='" + suffix + "'")
        _LOGGER.debug("Task assigned to thread: " + str(threading.current_thread().name))
        _LOGGER.debug("ID of process running task: " + str(os.getpid()))

        status = AggregatedCollectorResult()
        command = [self.tool_manager_output.toolpath, "-s"]
        status.addResult(self._collect_helper(command, outputDir, "statistics" ,suffix))
        command = [self.tool_manager_output.toolpath, "-a", "-n", "-v", "-e", "-p"]
        status.addResult(self._collect_helper(command, outputDir, "connections", suffix))
        return status

    def _collect_windows(self, outputDir, suffix):
        """Collects network statistics and current network connections in Windows.
        `netstat.exe` is required to run this collection.
        Collector gathers data and stores output in `.out` file and errors in `.err` file

        Parameters
        ----------
        outputDir : string
            Data collection directory path
        suffix : string
            Suffix to the file

        Returns
        -------
        CollectorResult
            CollectorResult.Success() if successful
            OR CollectorResult.Failure() if failure
            OR CollectorResult.Exception() otherwise
        """

        _LOGGER.info("Starting Netstat collector with: outputDir='" + outputDir + "' suffix='" + suffix + "'")
        _LOGGER.debug("Task assigned to thread: " + str(threading.current_thread().name))
        _LOGGER.debug("ID of process running task: " + str(os.getpid()))

        status = AggregatedCollectorResult()
        command = [self.tool_manager_output.toolpath, "-s"]
        status.addResult(self._collect_helper(command, outputDir, "statistics", suffix))
        command = [self.tool_manager_output.toolpath, "-a", "-n", "-o"]
        status.addResult(self._collect_helper(command, outputDir, "connections", suffix))
        return status

    def _collect_helper(self, command, outputDir, prefix, suffix):
        fname = os.path.join(outputDir, "netstat_" + prefix + suffix)
        with open(fname + ".out", "a+") as output, open(fname + ".err", "a+") as error:
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

Serializable.register(NetStat)
