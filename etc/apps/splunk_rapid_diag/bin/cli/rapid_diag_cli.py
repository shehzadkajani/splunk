# python imports
from __future__ import absolute_import
import sys
import json
import glob
import os
import shutil
import time
import threading
import errno
import socket

sys.path.append(os.path.realpath(os.path.dirname(os.path.dirname(__file__))))
sys.path.append(os.path.realpath(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.append(os.path.join(os.path.realpath(os.path.dirname(os.path.dirname(__file__))), "splunklib"))

from six.moves.configparser import ConfigParser, NoSectionError, NoOptionError

# local imports
import logger_manager as log
from cli.cli_error_code import ErrorCodes
from rapid_diag.serializable import Serializable
from rapid_diag.util import get_splunkhome_path, get_templates_path, getConfStanza, splunk_login 
from rapid_diag.task import Task
from rapid_diag.task_handler import TaskHandler
from rapid_diag.task import CollectorAborter
from rapid_diag.process_abstraction import ProcessLister
from rapid_diag.collector.collector import Collector
from rapid_diag.collector.trigger.log_monitor import LogMonitor
from rapid_diag.collector.trigger.search_debug import SearchDebug
from rapid_diag.collector.trigger.periodic import Periodic
from rapid_diag.collector.trigger.resource_monitor import ResourceMonitor
from rapid_diag.collector.trigger.resource_monitor_trackers import MovingAverageResourceMonitorTracker
from rapid_diag.collector.diag import Diag
from rapid_diag.collector.ps import PS
from rapid_diag.collector.iops import IOPS
from rapid_diag.collector.lsof import LSOF
from rapid_diag.collector.stack_trace import StackTrace
from rapid_diag.collector.netstat import NetStat
from rapid_diag.collector.system_call_trace import SystemCallTrace
from rapid_diag.collector.network_packet import NetworkPacket
from rapid_diag.collector.search_result import SearchResult
from rapid_diag.collector.trigger.periodic import Periodic

_LOGGER = log.setup_logging("cli", True)

def animate_collection(func):
    # nonlocal is not available in python2
    animate_collection.done = False

    def animate():
        while not animate_collection.done:
            # use stdout directly as it's not really a message
            sys.stdout.write('.')
            sys.stdout.flush()
            time.sleep(1)

    def collection_runner(*args):
        t = threading.Timer(1, animate)
        t.start()
        try:
            result = func(*args)
        finally:
            animate_collection.done = True
        return result

    return collection_runner

def get_tracker_obj(metric, threshold, invert):
    target = 'system'
    collector = MovingAverageResourceMonitorTracker.resource_factory.build(target, metric)
    num_samples = 10
    return MovingAverageResourceMonitorTracker(collector, threshold, num_samples, invert)


class RapidDiagCLI(object):
    def __init__(self):
        pass

    @staticmethod
    def task_template_list():
        list = RapidDiagCLI.get_static_tasks(get_templates_path())
        # error_list to display json validation errors at end of the task list.
        error_list = []

        for task in list:
            if "task" in task:
                task = task["task"]
            try:
                RapidDiagCLI.show_template(task)
            except Exception as e:
                error_list.append(str(e) + '\n' + str(task) + '\n')

        if error_list:
            _LOGGER.error("\n".join(error_list))
            return ErrorCodes.JSON_VALIDATION

        return 0

    @staticmethod
    def show_template(task_dict):
        taskInst = RapidDiagCLI.load_task_json(json.dumps(task_dict))
        if not taskInst:
            return ErrorCodes.JSON_VALIDATION
        _LOGGER.info(repr(taskInst))
        return 0

    @staticmethod
    def get_server_name():
        """Read the system's server.conf file and returns server name
        
        Returns
        -------
        [string]
            server name
        """
        conf_info = getConfStanza('server', 'general')
        try:
            if conf_info:
                return conf_info.get("serverName")
        except NoSectionError:
            _LOGGER.error("Host not found, Section not found in server.conf")
        except NoOptionError:
            _LOGGER.error("Host not found, Option not found in server.conf")
        except Exception as e:
            _LOGGER.error("Host not found, " + str(e))

        try:
            return socket.gethostname()
        except Exception as e:
            _LOGGER.error("Warning: Error getting host from os: " + str(e))
        return ""

    @staticmethod
    @animate_collection
    def run_task_template(args):
        _LOGGER.info("Running template with id=" + args.task_id)
        template_tasks = RapidDiagCLI.get_static_tasks(get_templates_path())
        for task in template_tasks:
            if task['task_id'] == args.task_id:
                if not RapidDiagCLI.load_task_json(json.dumps(task)):
                    return ErrorCodes.JSON_VALIDATION
                _LOGGER.info("Starting execution of %s" % (args.task_id))
                task_id = TaskHandler.build_task_id(task["name"], task.get("host", ""))
                task.update({'task_id': task_id})
                
                local_host = RapidDiagCLI.get_server_name()
                if local_host:
                    task.update({'host': local_host})
                try:
                    RapidDiagCLI.show_template(task)
                    task = TaskHandler().create(json.dumps(task), '')
                    run_info = RapidDiagCLI.get_run_info_object(task)
                    if not run_info:
                        _LOGGER.error("Collection details not found.")
                        return errno.ENOENT
                    else:
                        _LOGGER.info("Collection finished: " + Task.RunInfo.get_status_strings(run_info.status))
                        _LOGGER.info("Collection completed after " + str(run_info.finishTime - run_info.startTime))
                        _LOGGER.info("Output saved in: " + str(run_info.output_directory))
                        if run_info.status == Task.RunInfo.SUCCESS : return 0
                        if run_info.status == Task.RunInfo.ABORTED : return ErrorCodes.ACTION_ABORTED
                        return ErrorCodes.COLLECTION_FAILED
                except Exception as e:
                    _LOGGER.error(" Unhandled exception: " + str(e))
                    return 3
                return 0
        else:
            _LOGGER.error("Template with id=" + args.task_id + " not found in SampleTasks.")
            return errno.ENOENT

    @staticmethod
    def get_run_info_object(task):
        """
        returns run_info object of current task
        """
        try:
            run_info_list = TaskHandler()._get_tasks()
            for run_info in run_info_list:
                if task.task_id == run_info.task.task_id:
                    return run_info
            return None
        except Exception as e:
            _LOGGER.error("get_run_info_object: " + str(e))
            return None

    @staticmethod
    def get_static_tasks(path, match_file="*.json"):
        tasks = []

        for filename in glob.glob(os.path.join(path, match_file)):
            try:
                with open(filename, 'r') as f:
                    task_str = f.read()
                    task_dict = json.loads(task_str)
                    if task_dict.get("task"):
                        task_dict = task_dict.get("task")
                    tasks.append(task_dict)
            except Exception as e:
                _LOGGER.error("Error loading json file: {}".format(e) + ' File name: ' + str(filename))
        return tasks

    @staticmethod
    def json_upload(args):
        filepath = args.file

        if os.path.isfile(os.path.join(filepath)):
            if not os.access(filepath, os.R_OK):
                return errno.EACCES

            if not os.access(get_templates_path(), os.W_OK):
                return errno.EACCES

            try:
                with open(filepath, "r") as task:
                    task_dict = json.loads(task.read())
                    if 'task' in task_dict:
                        task_dict = task_dict['task']
                    if not RapidDiagCLI.load_task_json(json.dumps(task_dict)):
                        return ErrorCodes.JSON_VALIDATION
                    task_id = task_dict['task_id']

                template_tasks = RapidDiagCLI.get_static_tasks(get_templates_path())
                for task in template_tasks:
                    if task['task_id'] == task_id:
                        return ErrorCodes.DUPLICATE_TASK_ID

                return RapidDiagCLI.file_copy(filepath, name=args.name, forced=args.force)

            except ValueError as de:
                _LOGGER.error("Upload failed: " + str(de))
                return ErrorCodes.JSON_VALIDATION
            except Exception as e:
                _LOGGER.error("Uploadig json failed: " + str(e))
                return 3
        else:
            _LOGGER.error("No file name: %s" % (filepath))
            return errno.ENOENT

    @staticmethod
    def file_copy(filepath, name, forced):
        filename = filepath.rpartition(os.sep)[-1]
        if name:
            filename = name
        filename_dst = os.path.join(get_templates_path(), filename)
        if not forced and os.path.isfile(filename_dst):
            return errno.EEXIST

        shutil.copy(filepath, filename_dst)
        RapidDiagCLI.print_specific_dict(filename)
        _LOGGER.info("Successfully imported")
        return 0

    @staticmethod
    def print_specific_dict(filename):
        task_dict = RapidDiagCLI.get_static_tasks(get_templates_path(), filename)
        RapidDiagCLI.show_template(task_dict[0])

    @staticmethod
    def load_task_json(task_str):
        task = None
        try:
            task = json.loads(task_str, object_hook=Serializable.jsonDecode)
        except KeyError as e:
            _LOGGER.error("Key " + str(e) + " not found.")
        except Exception as e:
            _LOGGER.error(str(e))
        return task

    @staticmethod
    def invoke_collector(mode, name, args):
        _LOGGER.info("Collecting '%s' mode=%s, output_dir=%s, suffix=%s" % (name, mode, args.output_dir, args.suffix))
        token=None

        if name == "ps":        c = PS()
        elif name == "diag":    c = Diag()
        elif name == "netstat": c = NetStat()
        elif name == "search":  
            _LOGGER.info("Collector '%s' requires Splunk authentication." % name)
            token=splunk_login()
            c = SearchResult(search_query=args.search_query); 
        elif name == "iostat":  c = IOPS(collection_time=args.collection_time)
        elif name == "pstack":  c = StackTrace(process=ProcessLister.build_process(args.name, 
                                                                                    args.pid,
                                                                                    args.ppid, 
                                                                                    [args.args]))
        elif name == "lsof":    c = LSOF(process=ProcessLister.build_process(args.name, 
                                                                                args.pid, 
                                                                                args.ppid, 
                                                                                [args.args]))
        elif name == "strace":  c = SystemCallTrace(collection_time=args.collection_time, 
                                                    process=ProcessLister.build_process(args.name, 
                                                                                        args.pid, 
                                                                                        args.ppid, 
                                                                                        [args.args]))
        elif name == "tcpdump": c = NetworkPacket(collection_time=args.collection_time, 
                                                  ip_address=args.ip_address, port=args.port)
        else:
            _LOGGER.error("Invalid or unsupported collector request: " + name)
            return 1


        if mode == "periodic-collect":
            periodic_obj = Periodic(sampleCount=args.sample_count, interval=args.interval)
            periodic_obj.add(c)
            c = periodic_obj
        elif mode == "resource-monitor":
            metrics = {"cpu": args.cpu, "physical_memory": args.physical_memory, "virtual_memory": args.virtual_memory}
            trackers = []
            for metric, value in metrics.items():
                if value:
                    trackers.append(get_tracker_obj(metric, value, args.invert))

            resource_monitor_obj = ResourceMonitor(trackers)
            resource_monitor_obj.add(c)
            c = resource_monitor_obj
        elif mode == "log-monitor":
            log_monitor_obj = LogMonitor(args.log_file, args.regex)
            log_monitor_obj.add(c)
            c = log_monitor_obj
        elif mode == "search-debug":
            search_debug_obj = SearchDebug(args.regex, [c])
            c = search_debug_obj
        elif mode != "collect":
            _LOGGER.error("Invalid or unsupported mode request: " + mode)
            return 2

        with CollectorAborter([c]):
            run_context = Collector.RunContext(args.output_dir, args.suffix, token)
            result = c.collect(run_context)
            _LOGGER.info("Collection finished: " + result.getStatusString())
            _LOGGER.info("Output saved in: " + args.output_dir)

        if result.isSuccess(): return 0
        if result.isAborted(): return ErrorCodes.ACTION_ABORTED
        return ErrorCodes.COLLECTION_FAILED
