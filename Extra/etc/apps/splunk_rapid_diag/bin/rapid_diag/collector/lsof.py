# python imports
from __future__ import print_function, absolute_import
import os
import re
import sys
import threading
import tempfile
import shutil

# if collector is ran from CLI
SPLUNK_HOME = os.environ.get('SPLUNK_HOME')
SPLUNK_DB = os.environ.get('SPLUNK_DB')
if not SPLUNK_HOME or not SPLUNK_DB:
    print('ERROR: SPLUNK_HOME and SPLUNK_DB must be set in environment path.\nExecute the file via Splunk\'s python e.g $SPLUNK_HOME/bin/splunk cmd python <file_name.py>', file=sys.stderr)
    exit(1)
sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.realpath(__file__)))))


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
from rapid_diag.process_abstraction import ProcessLister

_LOGGER = log.setup_logging("lsof")
IS_LINUX = sys.platform.startswith('linux')


NO_TASK_MSG = "no tasks located"
NO_PROCESS_ID_MSG = "process ID not located"


class LSOF(Collector, ToolsCollector, Serializable):
    """ RapidDiag collector allows collecting list of open files by given process """

    def __init__(self, process, state=Collector.State.WAITING):
        Collector.__init__(self)
        ToolsCollector.__init__(self, valid_return_code=[0, None])
        self.process = process
        self.state = state
        self.tool_name = self.get_tool_name()
        self.tool_manager_output = ToolAvailabilityManager.find(self.tool_name)

    @staticmethod
    def get_tool_name():
        """
        TODO: Change handle64 to handle
        ISSUE: In windows os handle internally starts up handle64 as a child. 
        At the time of running a handle with subprocess it popups the console 
        output instead of writing output to *.out file. The solution for this 
        is to use STARTF_USESHOWWINDOW dwflag with startupinfo and hide the 
        window output. But neither our creation flags and startupinfo can be 
        clubbed together nor creation flags can be removed(creation flags were 
        used as a workaround for other problems).
        Changes are also required in resource.py
        """
        return ("lsof" if IS_LINUX else "handle64.exe")

    @staticmethod
    def tool_missing():
        utility_name = LSOF.get_tool_name()
        tool_manager = SessionGlobals.get_tool_availability_manager()
        is_avail = tool_manager.is_available(utility_name)
        if is_avail:
            return None

        tempDir = tempfile.mkdtemp()
        try:
            process = ProcessLister.build_process_from_pid(os.getpid())
            dummy_obj = LSOF(process)
            _ = dummy_obj.collect(Collector.RunContext(tempDir, '', None))
            message = tool_manager.get_tool_message(utility_name)
            message = None if message == True else message
        finally:
            shutil.rmtree(tempDir, True)
        return message

    def get_custom_display_name(self):
        return self.process.get_custom_display_name()

    def get_process_name(self):
        return self.process.get_process_name()

    def getType(self):
        return Type.SNAPSHOT

    def get_required_resources(self):
        if not IS_LINUX:
            return [Resource('handle64')]
        return [Resource('lsof', self.process)]

    def toJsonObj(self):
        return {
            'process': self.process,
            'state': Collector.State.get_status_string(self.state)
        }

    def __repr__(self):
        return "LSOF(Process: %r)" % (self.process)

    @staticmethod
    def validateJson(obj):
        data_types = {"process": (object,)}
        for field in list(filter(lambda x: x in obj.keys(), data_types.keys())):
            Serializable.check_data_type(obj[field], data_types[field], field)

    @staticmethod
    def fromJsonObj(obj):
        return LSOF(obj['process'], Collector.State.get_status_code(obj.get("state")))

    def _collect_impl(self, runContext):
        tool_manager = SessionGlobals.get_tool_availability_manager()
        if not self.preflightChecks():
            tool_manager.set_available(self.tool_name, self.tool_manager_output.error_message)
            return CollectorResult.Failure()

        if self.tool_manager_output.error_message is not None:
            status = CollectorResult.Failure(self.tool_manager_output.error_message, _LOGGER)
        else:
            self.promote_state(Collector.State.COLLECTING, runContext.stateChangeObservers)
            collectFun = self._collect_linux if IS_LINUX else self._collect_windows
            status = collectFun(runContext.outputDir, runContext.suffix)
        tool_worked = status.isSuccess() or self.get_state() == Collector.State.ABORTING
        tool_manager.set_available(self.tool_name, True if tool_worked else self.tool_manager_output.error_message)
        return status

    def _collect_helper(self, command, fname):
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

    def _collect_windows(self, outputDir, suffix):
        """ For windows, collect list of open files by given process using handle utility."""
        _LOGGER.info('Starting lsof collector using handle: collect with process=' + str(self.process) + ' outputDir=' + outputDir + ' suffix=' + suffix)
        _LOGGER.debug("Task assigned to thread: " + str(threading.current_thread().name))
        _LOGGER.debug("ID of process running task: "+str(os.getpid()))

        fname = os.path.join(outputDir, 'handle64_' + str(self.pid) + suffix)

        command = [self.tool_manager_output.toolpath, '-a', '-nobanner', '-p',  str(self.pid), '-accepteula']
        _LOGGER.debug('Collecting ' + ' '.join(command) + ' into ' + outputDir + ' suffix ' + suffix)

        return self._collect_helper(command, fname)

    def _collect_linux(self, outputDir, suffix):
        """For Linux, collect list of open files by given process using lsof utility."""
        _LOGGER.info('Starting lsof collector using lsof: collect with process=' +str(self.process) + ' outputDir=' + outputDir + ' suffix=' + suffix)
        _LOGGER.debug("Task assigned to thread: " +
                      str(threading.current_thread().name))
        _LOGGER.debug("ID of process running task: "+str(os.getpid()))

        # TODO: -E only works in newer versions of lsof (version greater or equal to 4.89)
        command = [self.tool_manager_output.toolpath, '-s', '-V', '-n', '-a', '-K', '-p', str(self.pid)]
        
        fname = os.path.join(outputDir, 'lsof_' + str(self.pid) + suffix)

        result = self._collect_helper(command, fname)


        if result.status == CollectorResult.FAILURE:
            output_string = None
            with open(fname + ".out", "r") as output:
                output_string = output.read()

            # if -K option fails rerun the lsof without -K option.
            if (not NO_PROCESS_ID_MSG in output_string) and NO_TASK_MSG in output_string:
                _LOGGER.info('Rerunnig lsof collector using lsof without -K option: collect with process=' + str(
                    self.process) + ' outputDir=' + outputDir + ' suffix=' + suffix)
                command.remove("-K")
                result = self._collect_helper(command, fname)
        return result

    def preflightChecks(self):
        return self.__checkProcess() and self.__checkAccess()

    def __checkProcess(self):
        best_match = SessionGlobals.get_process_lister().get_best_running_match(self.process)
        if best_match:
            self.process = best_match
            self.pid = best_match.get_pid()
            return True
        else:
            _LOGGER.error(
                "Can't read data for process=" + str(self.process) + ": process not running")
            return False

    def __checkAccess(self):
        if IS_LINUX:
            if not os.access('/proc/' + str(self.pid), os.R_OK | os.X_OK):
                _LOGGER.error(
                    "Can't read data for process=" + str(self.process) + " from path " + '/proc/' + str(self.pid) + ": insufficient permissions")
                return False
        return True


Serializable.register(LSOF)
