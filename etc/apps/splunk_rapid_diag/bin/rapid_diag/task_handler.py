# python imports
from __future__ import print_function, absolute_import
import os
import sys
import time
import json
import glob
import signal
import subprocess
import filelock
import copy

# local imports
import logger_manager as log
from rapid_diag.task import Task
from rapid_diag.serializable import Serializable
from rapid_diag.util import build_rapid_diag_timestamp, flatten_collectors, remove_empty_directories, get_splunkhome_path, bytes_to_str
from rapid_diag.process_abstraction import ProcessLister, ProcessNotFound
from rapid_diag.collector.performance_counter import PerformanceCounterStarted
import rapid_diag.collector.resource_manager


# constants
_LOGGER = log.setup_logging("task_handler")
IS_LINUX = sys.platform.startswith('linux')
resource_manager_mod = lambda: rapid_diag.collector.resource_manager
TEMPLATE_TASK_PATH = get_splunkhome_path(
            ["etc", "apps", "splunk_rapid_diag", "SampleTasks"])
HISTORIC_TASK_PATH = get_splunkhome_path(["etc","apps", "splunk_rapid_diag", "tasks"])


class TaskHandler(object):
    """
    Task Handler for CRUD and list operations.
    """
    def __init__(self):
        self.task_script_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))), "tasks")

    @staticmethod
    def build_task_id(task_name, host_name):
        task_id = task_name + '_' + host_name + '_' + build_rapid_diag_timestamp()
        return task_id[-250:]

    def create(self, taskConf, sessionToken):
        """
        This method creates task based on request from splunk rapid_diag UI.
        """
        try:
            task = json.loads(taskConf, object_hook=Serializable.jsonDecode)
            for collector in flatten_collectors(task.collectors):
                collector.init_state()
            # check to based on task listing to block parallel runs of same collector(s)
            # not blocking in case of diag and search result collector
            if not resource_manager_mod().ResourceManager(task.collectors).should_start_task():
                _LOGGER.info("A task with identical collector(s) is already running.")
                run_info = Task.RunInfo(task, ProcessLister.build_process_from_pid(os.getpid()), Task.RunInfo.NONE, time.time(), time.time())
                run_info.save()

                with run_info:
                    run_info.finish('Failure')
                return

            # Task Execution based on multiprocessing
            if task.save(self.task_script_dir):
                # right now multi-processing is not working with splunk's rest handler
                # p = mp.Process(target=task.run)
                task.run(sessionToken)
                return task
            return None
        except:
            _LOGGER.exception("Creating task has failed")

    def delete(self, task_str):
        task_info = json.loads(task_str, object_hook=Serializable.jsonDecode)

        try:
            if not os.path.exists(task_info.getOutputDir()):
                return

            if task_info.is_running():
                return
            
            task_info.remove_task()
            
        except Exception as e:
            _LOGGER.exception('Unable to delete the task ' + str(task_info['name']) + " - " + str(e))


    def abort(self, task_str):
        run_info = json.loads(task_str, object_hook=Serializable.jsonDecode)
        if not run_info.is_running():
            return

        try:
            with run_info:
                with open(run_info.getRunInfoPath(), 'r') as f:
                    task = f.read()
                    run_info = json.loads(task, object_hook=Serializable.jsonDecode)
                    if not run_info.is_running():  # checked again after locking and now it's finished -- skip!
                        return

                status_before_aborting = copy.deepcopy(run_info.status)
                run_info.promote_state_to(Task.RunInfo.ABORTING)
                process = run_info.process

                try:
                    sysproc = ProcessLister.build_process_from_pid(process.get_pid())
                    if not (process.get_process_name() == sysproc.get_process_name() and process.get_process_arguments() == sysproc.get_process_arguments()):
                        run_info.finish('Failure')
                        return

                    pid = process.get_pid()
                    _LOGGER.info("Aborting the task with pid "+ str(pid))
                    if IS_LINUX:
                        os.kill(pid, signal.SIGINT)
                    else:
                        # in case of windows we are force killing the task
                        # force killing in windows kills the whole process tree
                        # after force killing doing the necessary cleanup for system call trace and network packet collectors
                        # zipping the generated pml files in case of procmon
                        # running the `netsh trace stop` command in case of netsh, otherwise it won't startup next time

                        # if diag is aborted, data generated for it will be zero kb(in case of windows only)
                        process = subprocess.Popen(['taskkill', '/F', '/T', '/PID', str(pid)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        out, err = process.communicate()  # returns bytes strings
                        # if process does not exist, then 128 is the return code for it
                        if process.poll() == 128:
                            _LOGGER.error('Unable to abort the task with pid ' + str(pid) + '. No such process.')
                            run_info.finish('Failure')
                            return

                        # in case if access is denied to kill the process or any other errors
                        if err:
                            _LOGGER.error('Unable to abort the task with pid ' + str(pid) + '.\nstderr=' + bytes_to_str(err))
                            run_info.promote_state_to(status_before_aborting)
                            return

                        for collector in flatten_collectors(run_info.task.collectors):
                            collector.cleanup(output_directory=run_info.getOutputDir(), suffix='_' + run_info.getOutputDir().split(Task.RunInfo.getHashedString(run_info.task.name) + '_')[1])

                        # archiving the collected data and changing status to Aborted
                        run_info.task.archive(run_info.getOutputDir(), 'Aborted', run_info.getFinishedOutputDir())
                        # This is to avoid running paths getting written in outer JSON
                        run_info.output_directory = None
                        run_info.finish('Aborted')
                except:
                    _LOGGER.exception('Unable to abort the task with pid ' + str(pid))
                    run_info.promote_state_to(status_before_aborting)
        except filelock.Timeout as flt:
            _LOGGER.error("Could not successfully abort the task. Error acquiring lock to file " + str(run_info.getRunInfoPath()) + ": " + str(flt))

    def _cleanup(self, unfinished_tasks):
        for idx, runInfo in enumerate(unfinished_tasks):
            mark_failed = False
            with runInfo as ri:  # acquire lock
                with open(runInfo.getRunInfoPath(), 'r') as f:
                    task = f.read()
                    unfinished_tasks[idx] = json.loads(task, object_hook=Serializable.jsonDecode)
                    if unfinished_tasks[idx].is_finished():  # checked again after locking and now it's finished -- skip!
                        continue
                process = unfinished_tasks[idx].process
                try:
                    sysproc = ProcessLister.build_process_from_pid(process.get_pid())
                    if not (process.get_process_name() == sysproc.get_process_name() and process.get_process_arguments() == sysproc.get_process_arguments()):
                        mark_failed = True
                except ProcessNotFound:
                    _LOGGER.error('Unable to find a matching process for pid: {!s}'.format(process.get_pid()))
                    mark_failed = True

            if mark_failed:
                if not IS_LINUX:
                    # remove counter here so that if IOPS is selected in windows its counter gets
                    # removed and it doesn't keep on collecting data
                    PerformanceCounterStarted(ri.getOutputDir(), '').remove_counter()
                with unfinished_tasks[idx]:
                    unfinished_tasks[idx].finish('Failure')
                # unfinished_tasks[idx].promote_state_to(Task.RunInfo.FAILURE)
        return unfinished_tasks

    def _get_tasks(self, host=None, running_dir=''):
        tasks = []
        if running_dir:
            tasks_to_clean = []
        for filename in glob.glob(os.path.join(rapid_diag.task.DEFAULT_OUTPUT_ROOT, running_dir, '*', '*', '*.json')):
            try:
                with open(filename, 'r') as f:
                    task = f.read()
                    run_info = json.loads(task, object_hook=Serializable.jsonDecode)
                    if running_dir and run_info.task.host == host:
                        tasks_to_clean.append(run_info)
                    else:
                        tasks.append(run_info)
            except Exception as e:
                _LOGGER.exception("Error loading task from file name " + str(filename) + ": " + str(e))
        if running_dir:
            return tasks + self._cleanup(tasks_to_clean)
        return tasks

    def list(self, host):
        """
        Method to list all collection tasks.
        """
        remove_empty_directories(os.path.join(rapid_diag.task.DEFAULT_OUTPUT_ROOT, 'running'))

        finished_tasks = self._get_tasks()
        unfinished_tasks = self._get_tasks(host, 'running')
        tasks = unfinished_tasks + finished_tasks
        for idx, task in enumerate(tasks):
            task_dict = json.loads(json.dumps(task, indent=4, default=Serializable.jsonEncode))
            tasks[idx] = task_dict
        return tasks

    @staticmethod
    def _get_static_tasks(path):
        tasks = []
        for filename in glob.glob(os.path.join(path, "*.json")):
            try:
                with open(filename, 'r') as f:
                    task_str = f.read()
                    task = json.loads(task_str, object_hook=Serializable.jsonDecode)
                    task_dict = json.loads(task_str)
                    if task_dict.get("task"):
                        task_dict = task_dict.get("task")
                        task_str = json.dumps(task_dict)
                    tasks.append(task_dict)
            except Exception as e:
                _LOGGER.exception("Error loading task from file name " + str(filename) + ": " + str(e))

        return tasks

    def static_tasks_list(self):
        """
        Method to list add pre configured tasks
        """
        template_tasks = TaskHandler._get_static_tasks(TEMPLATE_TASK_PATH)
        historical_tasks = TaskHandler._get_static_tasks(HISTORIC_TASK_PATH)

        return {"template_tasks": template_tasks, "historical_tasks" : historical_tasks}


if __name__ == '__main__':
    """
    Should only be used for debugging purposes by running it independently
    """
    import tempfile
    import logging

    _LOGGER.setLevel(logging.DEBUG)
    _LOGGER.addHandler(logging.StreamHandler())

    taskConf = {
        "__class__": "rapid_diag.task.Task",
        "collectors": [
            {
                "__class__": "rapid_diag.collector.trigger.resource_monitor.ResourceMonitor",
                "resource_monitor_trackers": [
                    {
                        "__class__": "rapid_diag.collector.trigger.resource_monitor_trackers.MovingAverageResourceMonitorTracker",
                        "target": "system",
                        "metric": "cpu",
                        "threshold": 10.0,
                        "num_samples": 10,
                        "invert": False
                    },
                    {
                        "__class__": "rapid_diag.collector.trigger.resource_monitor_trackers.MovingAverageResourceMonitorTracker",
                        "target": "system",
                        "metric": "physical_memory",
                        "threshold": 1000.0,
                        "num_samples": 10,
                        "invert": False
                    },
                    {
                        "__class__": "rapid_diag.collector.trigger.resource_monitor_trackers.MovingAverageResourceMonitorTracker",
                        "target": "system",
                        "metric": "virtual_memory",
                        "threshold": 1000.0,
                        "num_samples": 10,
                        "invert": False
                    }
                ],
                "collectors": [
                    {
                        "__class__": "rapid_diag.collector.trigger.periodic.Periodic",
                        "collectors": [
                            {
                                "__class__": "rapid_diag.collector.system_call_trace.SystemCallTrace",
                                "collection_time": 1000,
                                "process": {
                                    "__class__": "rapid_diag.process_abstraction.Process",
                                    "args": "\"C:\\Program Files\\Splunk\\bin\\splunkd.exe\" service",
                                    "name": "splunkd",
                                    "pid": 4567,
                                    "ppid": 1234,
                                    "process_type": "splunkd server"
                                }
                            },
                            {
                                "__class__": "rapid_diag.collector.stack_trace.StackTrace",
                                "process": {
                                    "__class__": "rapid_diag.process_abstraction.Process",
                                    "args": "\"C:\\Program Files\\Splunk\\bin\\splunkd.exe\" service",
                                    "name": "splunkd",
                                    "pid": 4567,
                                    "ppid": 1234,
                                    "process_type": "splunkd server"
                                }
                            },
                            {
                                "__class__": "rapid_diag.collector.network_packet.NetworkPacket",
                                "collection_time": 10
                            },
                            {
                                "__class__": "rapid_diag.collector.iops.IOPS",
                                "collection_time": 15
                            },
                            {
                                "__class__": "rapid_diag.collector.netstat.NetStat"
                            },
                            {
                                "__class__": "rapid_diag.collector.ps.PS"
                            },
                            {
                                "__class__": "rapid_diag.collector.lsof.LSOF",
                                "process": {
                                    "__class__": "rapid_diag.process_abstraction.Process",
                                    "args": "\"C:\\Program Files\\Splunk\\bin\\splunkd.exe\" service",
                                    "name": "splunkd",
                                    "pid": 4567,
                                    "ppid": 1234,
                                    "process_type": "splunkd server"
                                }
                            }
                        ],
                        "interval": 10.0,
                        "sampleCount": 10
                    },
                ]
            },
            {
                "__class__": "rapid_diag.collector.diag.Diag"
            }
        ],
        "name": "test_task",
        "description": "",
        "host": "local",
        "task_id": "test_task_local_2019-04-11T10h47m57s486861ms",
        "output_directory": tempfile.mkdtemp()
    }

    h = TaskHandler()
    h.create(json.dumps(taskConf), '')

    print(h.list('local'))
