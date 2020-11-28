# python imports
from __future__ import absolute_import
import os
import json
import time
import datetime
import tarfile
import math
import sys
import signal
import filelock
import shutil
import hashlib
import errno

# local imports
from splunklib import six
import logger_manager as log
from rapid_diag.task_repr_generator import TaskReprGenerator
from rapid_diag.serializable import Serializable
from rapid_diag.util import build_rapid_diag_timestamp, flatten_collectors, str_to_bytes
from rapid_diag.conf_util import RapidDiagConf
from rapid_diag.collector.collector import Collector, CollectorStateObserver
from rapid_diag.collector import *
from rapid_diag.collector.trigger import *
from rapid_diag.collector.trigger.trigger import Trigger
from rapid_diag.session_globals import SessionGlobals
from rapid_diag.collector.collector_result import AggregatedCollectorResult, CollectorResult
from rapid_diag.process_abstraction import ProcessLister

_LOGGER = log.setup_logging("task")

DEFAULT_OUTPUT_ROOT = RapidDiagConf.get_general_outputpath()


class CollectorAborter(object):
    SIGNALS_HANDLED = [signal.SIGINT, signal.SIGTERM]
    SIGNALS_IGNORED = []
    if sys.platform.startswith("linux"):
        SIGNALS_HANDLED.append(signal.SIGALRM)
        SIGNALS_IGNORED.append(signal.SIGHUP)

    def __init__(self, collectors):
        self.collectors = collectors

    @staticmethod
    def __recursively_promote_collector_status(collectors):
        for collector in collectors:
            if collector.__module__.startswith('rapid_diag.collector'):
                collector.promote_state(Collector.State.ABORTING)
                if 'collectors' in collector.__dict__.keys():
                    CollectorAborter.__recursively_promote_collector_status(collector.collectors)

    def handler(self, signum, frame):
        _LOGGER.debug("Handling signal: " + str(signum))
        CollectorAborter.__recursively_promote_collector_status(self.collectors)

    def __enter__(self):
        self.handlers = {}
        for s in self.__class__.SIGNALS_HANDLED + self.__class__.SIGNALS_IGNORED:
            self.handlers[s] = signal.getsignal(s)
        for s in self.__class__.SIGNALS_HANDLED:
            signal.signal(s, self.handler)
        for s in self.__class__.SIGNALS_IGNORED:
            signal.signal(s, signal.SIG_IGN)

    def __exit__(self, type, value, traceback):
        for sig, handler in self.handlers.items():
            signal.signal(sig, handler)


class RunInfoStateChangeObserver:
    def __init__(self, run_info):
        self.run_info = run_info

    def __call__(self, collector, prev_state, new_state):
        if new_state == Collector.State.STARTED:
            if isinstance(collector, Trigger):
                with self.run_info:
                    self.run_info.promote_state_to(Task.RunInfo.MONITORING)
            else:
                with self.run_info:
                    self.run_info.promote_state_to(Task.RunInfo.COLLECTING)


class Task(Serializable):
    """
    RapidDiag task class to start particular collector
    """

    def __init__(self, name, description, collectors, host, task_id):
        self.name = name
        self.description = description
        self.collectors = collectors
        self.host = host
        self.task_id = task_id

    def run(self, sessionToken):
        '''
        Run separate thread/process to start the particular collector
        '''
        _LOGGER.debug("Collectors: " + str(self.collectors))

        process = ProcessLister.build_process_from_pid(os.getpid())

        runInfo = Task.RunInfo(self, process)
        runInfo.start()
        outputDir = runInfo.getOutputDir()
        runContext = Collector.RunContext(outputDir, '', sessionToken, [RunInfoStateChangeObserver(runInfo)])
        pool = SessionGlobals.get_threadpool()
        tokens = []
        diag_job = None

        with CollectorAborter(self.collectors):
            for job in self.collectors:
                if isinstance(job, diag.Diag):
                    diag_job = job
                else:
                    try:
                        tokens.append(self.start_collection(pool, job, runContext))
                    except Exception as e:
                        _LOGGER.exception('Exception while collecting data from ' + job.__class__.__name__)

            for token in tokens:
                token.wait()

            if diag_job:
                tokens.append(self.start_collection(pool, diag_job, runContext))
                tokens[-1].wait()

        with runInfo:
            runInfo.startArchival()

        result = AggregatedCollectorResult()
        for token in tokens:
            result.addResult(token.get_result())

        message = result.getStatusString()

        try:
            self.archive(outputDir, message, runInfo.getFinishedOutputDir())
        except Exception as e:
            result.addResult(CollectorResult.Exception(e, 'Exception while archiving files from outputDir=' + outputDir, _LOGGER))
            message = result.getStatusString()

        # set task status on task completion
        with runInfo:
            runInfo.finish(message)

    def start_collection(self, pool, job, runContext):
        curRunContext = runContext.clone()
        curRunContext.suffix = '_' + build_rapid_diag_timestamp()
        return pool.add_task(job.collect, curRunContext)

    def archive(self, root, message, output_directory=None):
        rootLen = len(root)
        jsonPath = ''
        rootDriveLen = len(os.path.splitdrive(root)[0])
        base = os.path.basename(root)
        runInfoPath = os.path.join(root, base)
        taskJsonPath = Task.RunInfo.getTaskJsonPath(root)
        with tarfile.open(root + '.tar.gz', 'w:gz') as tar:
            root, dirs, files = next(os.walk(root))
            for file in files:
                fullPath = os.path.join(root, file)
                if not os.stat(fullPath).st_size == 0 and file.endswith('.tar.gz'):
                    with tarfile.open(fullPath, 'r:gz') as srcTar:
                        try:
                            temp_root = root.replace("\\", "/")
                            for member in srcTar.getmembers():  # drive + root separator
                                if member.name.startswith(temp_root[:rootDriveLen+1]):
                                    member.name = member.name[rootDriveLen+1:]
                                if member.name.startswith(temp_root[rootDriveLen+1:]):
                                    member.name = member.name[rootLen-rootDriveLen:]
                                else:
                                    continue
                                member.name = os.path.join(base, member.name)
                                tar.addfile(member, srcTar.extractfile(member.name))
                        except IOError:
                            tar.add(fullPath, arcname=os.path.join(file.split('.tar.gz')[0], file), recursive=False)
                else:
                    if fullPath == taskJsonPath:
                        jsonPath = fullPath
                    elif not file.endswith('.lock') and not file.endswith('.pml'):
                        tar.add(fullPath, arcname=os.path.join(base, file))

                if fullPath not in [taskJsonPath, runInfoPath + '.json.lock']:
                    os.remove(fullPath)
            if jsonPath:
                with open(jsonPath, "r+") as file_handler:
                    json_data = json.loads(file_handler.read())
                    file_handler.seek(0)
                    file_handler.truncate()
                    json_data['status'] = message
                    # Updating the output_directory in case of abort to show finished path instead of running path
                    if output_directory:
                        json_data['output_directory'] = output_directory
                    file_handler.write(json.dumps(json_data, indent=4))
                tar.add(jsonPath, arcname=os.path.join(base, jsonPath.split(os.sep)[-1:][0]))

            for dir in dirs:
                try:
                    tar.add(os.path.join(root, dir), arcname=os.path.join(base, dir))
                except:
                    pass

    def __repr__(self):
        return repr(TaskReprGenerator(self))

    def toJsonObj(self):
        return {'name': self.name,
                'description': self.description,
                'collectors': self.collectors,
                'host': self.host,
                'task_id': self.task_id}

    @staticmethod
    def validateJson(obj):
        data_types = {"name": (six.text_type,), "description": (six.text_type, type(None)), "collectors": (list,), "task_id": (six.text_type, type(None))}
        for field in list(filter(lambda x: x in obj.keys(), data_types.keys())):
            Serializable.check_data_type(obj[field], data_types[field], field)

        value_range = {"name": [1, 256], "description": [0, 8192]}
        for field in list(filter(lambda x: x in obj.keys(), value_range.keys())):
            Serializable.check_value_in_range(
                len(obj[field].strip()), value_range[field], field)

        string_value = ["name"]
        for field in list(filter(lambda x: x in obj.keys(), string_value)):
            Serializable.check_string_value(obj[field], field)

        if not 'task_id' in obj.keys() or not len(obj["task_id"].strip()):
            raise ValueError("task_id : cannot be empty.")

        if 'collectors' not in obj.keys() or not len(obj['collectors']):
            raise Exception("Collector list can not be empty.")

    @staticmethod
    def fromJsonObj(obj):
        return Task(obj['name'].strip(), obj.get('description', '').strip(), obj['collectors'], obj.get('host', ''), obj.get('task_id', ''))

    def save(self, outputDir):
        '''
        Write the json object of task in particular TASK_NAME.json file
        :return: boolean value if task gets successfully written or not
        '''
        fname = os.path.join(outputDir, self.name + '.json')
        try:
            if not os.path.isdir(outputDir):
                os.makedirs(outputDir)
            with open(fname, 'w+') as f:
                json.dump(self, f, indent=4, default=Serializable.jsonEncode)
            return True
        except filelock.Timeout as flt:
            _LOGGER.error("Error saving task to " +
                          str(fname) + ": " + str(flt))
        except (IOError, OSError) as e:
            if e.errno == errno.EACCES:
                _LOGGER.exception(
                    "Permission denied: Please check the application's owner and/or permissions. For more information check the Troubleshooting section on the Help page.")
                return True
            _LOGGER.exception('Error writing task to ' +
                              str(fname) + '.\n' + str(e))
        except Exception as e:
            _LOGGER.exception('Error writing task to ' +
                              str(fname) + '.\n' + str(e))

        return False

    class RunInfo(Serializable, CollectorStateObserver):

        NONE = 0
        MONITORING = 1
        COLLECTING = 2
        ARCHIVING = 3
        ABORTING = 4
        FINISHED = 5
        SUCCESS = 6
        FAILURE = 7
        PARTIAL_SUCCESS = 8
        ABORTED = 9
        STATUS_STRINGS = {
            'None': NONE,
            'Monitoring': MONITORING,
            'Collecting': COLLECTING,
            'Archiving Results': ARCHIVING,
            'Aborting': ABORTING,
            'Finished': FINISHED,
            'Success': SUCCESS,
            'Failure': FAILURE,
            'Partial Success': PARTIAL_SUCCESS,
            'Aborted': ABORTED
        }

        def __init__(self, task, process, status=None, startTime=None, finishTime=None, output_directory=None):
            self.task = task
            self.process = process
            self.status = Task.RunInfo.NONE if status is None else status
            self.startTime = startTime
            self.finishTime = finishTime
            self.result = None
            self.flock = None
            self.output_directory = output_directory
            for collector in flatten_collectors(self.task.collectors):
                collector.registerObserver(self)

        def __repr__(self):
            return "RunInfo(task: %r, process: %r, status: %r, output_directory: %r)"%(self.task, self.process, self.status, self.output_directory)

        def __enter__(self, timeout=60):
            output_dir = self.getFinishedOutputDir()
            if not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir)
                except OSError as e:
                    if e.errno == errno.EACCES:
                        _LOGGER.exception(
                            "Permission denied: Please check the application's owner and/or permissions. For more information check the Troubleshooting section on the Help page.")
                    else:
                        _LOGGER.debug("While creating " +
                                    output_dir + ": " + str(e))
            self.flock = filelock.FileLock(self.getLockPath())
            self.flock.acquire(timeout)
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.flock.release()
            return None

        def getFilenamePrefix(self):
            timestamp = build_rapid_diag_timestamp(datetime.datetime.utcfromtimestamp(self.startTime))
            return Task.RunInfo.getHashedString(self.task.name) + '_' + timestamp

        def getLockPath(self):
            return os.path.join(self.getFinishedOutputDir(), self.getFilenamePrefix() + '.lock')

        def is_running(self):
            return self.status > Task.RunInfo.NONE and self.status < Task.RunInfo.ARCHIVING

        def is_finished(self):
            return self.status >= Task.RunInfo.FINISHED

        def promote_state_to(self, state):
            if self.status > state:
                return
            self.status = state
            self.save()

        @staticmethod
        def getHashedString(name):
            return hashlib.sha1(str_to_bytes(name)).hexdigest()

        @staticmethod
        def getTaskJsonPath(outputDir):
            return os.path.join(outputDir, 'task.json')

        def getRunningOutputDir(self):
            return os.path.join(DEFAULT_OUTPUT_ROOT, 'running', Task.RunInfo.getHashedString(self.task.name), self.getFilenamePrefix())

        def getFinishedOutputDir(self):
            return os.path.join(DEFAULT_OUTPUT_ROOT, Task.RunInfo.getHashedString(self.task.name), self.getFilenamePrefix())

        def getOutputDir(self):
            if self.is_finished():
                return self.getFinishedOutputDir()
            return self.getRunningOutputDir()

        @staticmethod
        def get_status_strings(state):
            state_list = [key for key, value in Task.RunInfo.STATUS_STRINGS.items() if value == state]
            if len(state_list) != 1:
                _LOGGER.warning("Invalid state=" + str(state) + ". Returning initial state.")
                return Task.RunInfo.get_status_strings(Task.RunInfo.NONE)
            return state_list[0]

        def getRunInfoPath(self):
            outputDir = self.getOutputDir()
            return os.path.join(outputDir, 'task.json')

        def start(self):
            self.startTime = time.time()
            self.finishTime = None

        def startArchival(self):
            # TODO advertise presence of errors somehow in the status
            self.finishTime = time.time()
            self.promote_state_to(Task.RunInfo.ARCHIVING)

        def finish(self, result):
            self.finishTime = time.time()
            self.result = result
            self.promote_state_to(Task.RunInfo.FINISHED)
            self.move_task()

        def move_task(self):
            # once finished, move the task outside of the running buffer directory
            source_dir = self.getRunningOutputDir()
            dest_dir = self.getFinishedOutputDir()
            collection_gz = source_dir + '.tar.gz'
            if os.path.exists(collection_gz):
                shutil.move(collection_gz, os.path.dirname(dest_dir))
            try:
                shutil.rmtree(source_dir)
            except OSError as oe:
                _LOGGER.warning("File " + self.getLockPath() + " gets autoremoved by filelock lib. Exception message: " + str(oe))
            except Exception as e:
                _LOGGER.error("Exception caught when removing path=" + self.getRunInfoPath() + " : " + str(e))

        def remove_task(self):
            outputDir = self.getOutputDir()
            try:
                if os.path.exists(outputDir):
                    shutil.rmtree(outputDir) 
            except OSError as oe:
                _LOGGER.error("OS Exception caught when removing path=" + str(outputDir) + ". Exception message: " + str(oe))
            except Exception:
                _LOGGER.error("Exception caught when removing path=" + str(outputDir))

        def setDuration(self):
            return math.ceil(self.finishTime - self.startTime) if self.finishTime is not None else math.ceil(time.time() - self.startTime)

        def __repr__(self):
            return "RunInfo(Task: \n%r, Process: %r, Status: %r)" % (self.task, self.process, self.status)

        def toJsonObj(self):
            obj = {
                'task': self.task,
                'name': self.task.name,
                'process': self.process,
                'status': Task.RunInfo.get_status_strings(self.status)
            }
            if self.startTime is not None:
                obj['created_at'] = self.startTime
                obj['output_directory'] = os.path.normpath(self.output_directory) if self.output_directory else self.getOutputDir()
            if self.finishTime is not None:
                obj['completed_at'] = self.finishTime
            if self.result:
                obj['status'] = self.result
            obj["duration"] = self.setDuration()
            return obj

        @staticmethod
        def validateJson(obj):
            data_types = {"task": (object,), "status": (six.text_type,), "process": (object)}
            for field in list(filter(lambda x: x in obj.keys(), data_types.keys())):
                Serializable.check_data_type(obj[field], data_types[field], field)

        @staticmethod
        def fromJsonObj(obj):
            status_int = Task.RunInfo.STATUS_STRINGS[obj['status']]
            assert(status_int != -1)
            return Task.RunInfo(obj['task'], obj['process'], status_int, obj.get('created_at', None), obj.get('completed_at', None), obj.get('output_directory', None))

        def save(self):
            try:
                if not os.path.exists(self.getOutputDir()):
                    try:
                        os.makedirs(self.getOutputDir())
                    except OSError as e:
                        if e.errno == errno.EACCES:
                            _LOGGER.exception(
                                "Permission denied: Please check the application's owner and/or permissions. For more information check the Troubleshooting section on the Help page.")
                        else:
                            _LOGGER.debug("While creating " +
                                        self.getOutputDir() + ": " + str(e))
                with open(self.getRunInfoPath(), 'w+') as f:
                    json.dump(self, f, indent=4, default=Serializable.jsonEncode)
            except filelock.Timeout as flt:
                _LOGGER.error("Error saving task status in " + self.getRunInfoPath() + ": " + str(flt))
            except (IOError, OSError) as e:
                if e.errno == errno.EACCES:
                    _LOGGER.exception(
                        "Permission denied: Please check the application's owner and/or permissions. For more information check the Troubleshooting section on the Help page.")
                _LOGGER.error("Error saving task status in " + self.getRunInfoPath() + ": " + str(e))
            except Exception as e:
                _LOGGER.exception("Error saving task status in " + self.getRunInfoPath() + ": " + str(e))


Serializable.register(Task)
Serializable.register(Task.RunInfo)
