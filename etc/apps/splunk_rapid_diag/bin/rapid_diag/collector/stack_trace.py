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
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))

# local imports
import logger_manager as log
from rapid_diag.collector.type import Type
from rapid_diag.collector.collector import Collector
from rapid_diag.collector.tools_collector import ToolsCollector
from rapid_diag.collector.resource import Resource
from rapid_diag.collector.collector_result import CollectorResult
from rapid_diag.collector.tool_manager import ToolAvailabilityManager
from rapid_diag.util import build_rapid_diag_timestamp
from rapid_diag.serializable import Serializable
from rapid_diag.session_globals import SessionGlobals
from rapid_diag.process_abstraction import ProcessLister
from rapid_diag.util import is_ptrace_allowed

_LOGGER = log.setup_logging("stack_trace")
IS_LINUX = sys.platform.startswith('linux')

REX_STDERR_NOT_LOGGABLE_LINE = re.compile('no matching address range')
REX_STDOUT_MAIN = re.compile('(?i)thread.*main')
REX_SYS_PROC_NOT_SUPPORTED = re.compile('System process is not supported')


class StackTrace(Collector, ToolsCollector, Serializable):
    """ RapidDiag collector allows collecting stack traces for a given process """

    def __init__(self, process, state=Collector.State.WAITING):
        Collector.__init__(self)
        # procdump returns -2 but python3 converts it to 4294967294(unsigned -2)
        # workaround, adding 4294967294 to valid_return_code
        # procdump should returns 0 for successful completion.
        # TODO: debug the issue and remove -2 and 4294967294 from the list.
        ToolsCollector.__init__(self, valid_return_code=[
                                0, 1] if IS_LINUX else [0, -2, 4294967294])
        self.process = process
        self.state = state
        self.tool_name = self.get_tool_name()
        self.tool_manager_output = ToolAvailabilityManager.find(self.tool_name)

    @staticmethod
    def get_tool_name():
        return ("eu-stack" if IS_LINUX else "procdump.exe")

    @staticmethod
    def tool_missing():
        utility_name = StackTrace.get_tool_name()
        tool_manager = SessionGlobals.get_tool_availability_manager()
        is_avail = tool_manager.is_available(utility_name)
        if is_avail:
            return None

        tempDir = tempfile.mkdtemp()
        try:
            process = ProcessLister.build_process_from_pid(os.getpid())
            dummy_obj = StackTrace(process)
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
            return [Resource('procdump')]
        return [Resource('ptrace', self.process)]

    def __repr__(self):
        return "Stack Trace(Process: %r)" % (self.process)

    def toJsonObj(self):
        return {
            'process': self.process,
            'state': Collector.State.get_status_string(self.state)
        }

    @staticmethod
    def validateJson(obj):
        data_types = {"process": (object,)}
        for field in list(filter(lambda x: x in obj.keys(), data_types.keys())):
            Serializable.check_data_type(obj[field], data_types[field], field)
    
    @staticmethod
    def fromJsonObj(obj):
        return StackTrace(obj['process'], Collector.State.get_status_code(obj.get("state")))

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

    def _collect_windows(self, outputDir, suffix):
        """For Windows, collects stack traces for a given process using procdump utility."""
        _LOGGER.info('Starting stack trace collector using procdump: collect with process=' + str(self.process) + ' outputDir=' + outputDir + ' suffix=' + suffix)
        _LOGGER.debug("Task assigned to thread: " + str(threading.current_thread().name))
        _LOGGER.debug("ID of process running task: "+str(os.getpid()))

        fname = os.path.join(outputDir, 'procdump_'+ str(self.pid) + suffix)
        command = [self.tool_manager_output.toolpath, str(self.pid), '-accepteula', outputDir]
        _LOGGER.debug('Collecting '+ ' '.join(command) + ' into ' + outputDir + ' suffix ' + suffix)

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

        with open(fname + ".out", "r") as out:
            if REX_SYS_PROC_NOT_SUPPORTED.search(out.read()):
                return CollectorResult.Failure("Writing a dump for the System process is not supported.",
                                            _LOGGER)

        return result


    def _collect_linux(self, outputDir, suffix):
        """For Linux, collects stack traces for a given process using eu-stack utility."""
        _LOGGER.info('Starting stack trace collector using eustack: collect with process=' +str(self.process) + ' outputDir=' + outputDir + ' suffix=' + suffix)
        _LOGGER.debug("Task assigned to thread: " +
                      str(threading.current_thread().name))
        _LOGGER.debug("ID of process running task: "+str(os.getpid()))

        # non-fatal, though it would be great if we could show in tool availability somehow...
        try:
            self.collectProc(outputDir, suffix)
        except EnvironmentError as e:
            _LOGGER.exception('Error collecting data from procfs, process=' +
                              str(self.process) + ' outputDir=' + outputDir + 
                              ' suffix=' + suffix + " exception: " + str(e))

        fname = os.path.join(outputDir, 'eustack_' + str(self.pid) + suffix)

        procCall = [self.tool_manager_output.toolpath, '-i', '-l', '-p', str(self.pid)]
        _LOGGER.debug('Collecting ' + ' '.join(procCall) + ' into ' + outputDir + ' with suffix ' + suffix)
        with open(fname + ".out", "a+") as output, open(fname + ".err", "a+") as error:    
            try:
                result = self.run(procCall, output, error)
            except EnvironmentError as e:
                return CollectorResult.Exception(e, 'Error collecting ' + str(self.tool_name) +
                                                ', please confirm you have the ' + str(self.tool_name) + ' package ' +
                                                'installed in your system and that the ' + str(self.tool_name) +
                                                ' command is available -- path=' + os.getenv('PATH'), _LOGGER)
            except Exception as e:
                return CollectorResult.Exception(e, 'Error collecting ' + str(self.tool_name), _LOGGER)

        if result not in self.valid_return_code:
            _LOGGER.error(
                self.tool_name + ' failed. This may be due to ptrace '
                'permissions. Please refer to the documentation for further '
                'details.')

        loggedError = False
        with open(fname + ".err", "r") as err:
            for line in err.read().splitlines():
                if not REX_STDERR_NOT_LOGGABLE_LINE.search(line):
                    if not loggedError:
                        _LOGGER.error(
                            'Stack trace collection finished with errors (see \"' + fname + '.err\")')
                        loggedError = True

        with open(fname + ".out", "r") as out:
            if (self.get_process_name().startswith("splunkd")) and (not REX_STDOUT_MAIN.search(out.read())):
                return CollectorResult.Failure("Latest stack dump (" + fname + ".out) doesn't " +
                                            "contain 'Thread's or 'main()' call! Please try " +
                                            "running manually and check output: " + ' '.join(procCall),
                                            _LOGGER)

        return result

    def collectProc(self, outputDir, suffix):
        base = '/proc/' + str(self.pid) + '/task'
        _LOGGER.debug('Collecting contents from path=' + base)
        with open(os.path.join(outputDir, 'kernelstack_' + str(self.pid) + suffix) + '.out', 'w') as k, \
                open(os.path.join(outputDir, 'status_' + str(self.pid) + suffix) + '.out', 'w') as s:
            for task in os.listdir(base):
                curBase = base + '/' + task
                _LOGGER.debug('Processing path=' + curBase)
                try:
                    k.write("Thread LWP " + task + "\n")
                    with open(curBase + '/stack', "r") as x:
                        k.write(x.read())
                except EnvironmentError as e:
                    _LOGGER.warning(
                        'Error collecting kernel stack data from procfs, process=' + str(self.process) + ' outputDir=' + outputDir + ' suffix=' + suffix + '\n' + str(e))
                    return "Error collecting kernel stack data from procfs"
                try:
                    s.write("Thread LWP " + task + "\n")
                    with open(curBase + '/status', "r") as x:
                        s.write(x.read())
                except EnvironmentError as e:
                    _LOGGER.warning('Error collecting status from procfs, process=' + str(self.process) + ' outputDir=' + outputDir + ' suffix=' + suffix + '\n' + str(e))
                    return "Error collecting status from procfs"
        return True

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


Serializable.register(StackTrace)
