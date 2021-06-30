# python imports
import os
import sys
import json

# Reloading the rapid_diag bin path
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from splunk.persistconn.application import PersistentServerConnectionApplication
from splunklib.binding import HTTPError

# local imports
import logger_manager as log
from rapid_diag_handler_utils import get_endpoint, persistent_handler_wrap_handle
from rapid_diag.task_handler import TaskHandler
from rapid_diag.collector.system_call_trace import SystemCallTrace
from rapid_diag.collector.stack_trace import StackTrace
from rapid_diag.collector.network_packet import NetworkPacket
from rapid_diag.collector.iops import IOPS
from rapid_diag.collector.netstat import NetStat
from rapid_diag.collector.ps import PS
from rapid_diag.collector.lsof import LSOF
from rapid_diag.task import DEFAULT_OUTPUT_ROOT
from rapid_diag.util import get_server_name
import rapid_diag.collector.resource_manager

_LOGGER = log.setup_logging("rapid_diag_info_endpoint")
resource_manager_mod = lambda: rapid_diag.collector.resource_manager


collector_class_map = {"system_call_trace": SystemCallTrace, "stack_trace": StackTrace, "network_packet": NetworkPacket, "iops": IOPS, "netstat":NetStat, "ps":PS, "lsof":LSOF}

def check_utilities():
    unavailable_utilities = {}
    # global collector_class_map
    for collector, klass in collector_class_map.items():
        message = klass.tool_missing()
        if message:
            unavailable_utilities[collector] = { klass.get_tool_name(): message }
    return unavailable_utilities


def check_allocated_resources(server):
    # TODO: use this in the UI later,
    # to not allow SystemCallTrace and StackTrace to run on same process
    running_tasks = TaskHandler()._get_tasks(server, 'running')
    allocated_resources = resource_manager_mod().ResourceManager().get_allocated_resources(running_tasks)
    return [resource.to_json() for resource in allocated_resources]


def check_running_collectors(host):
    handler = TaskHandler()
    tasks = handler.list(host)
    running_collectors = {}
    running_tasks = [task for task in tasks if task["task"]["host"] == host and task.get("status","") == "Collecting"]
    # global collector_class_map
    for collector in collector_class_map:
        if "rapid_diag.collector." + collector + "." in str(running_tasks):
            running_collectors[collector] = True
    return running_collectors


def get_collector_availability_status(session_key):
    host = get_server_name(session_key)
    running_collectors = check_running_collectors(host)
    unavailable_utilities = check_utilities()
    allocated_resources = check_allocated_resources(host)
    return {"unavailable_utilities": unavailable_utilities, "running_collectors": running_collectors, "splunk_server": host, "output_directory": DEFAULT_OUTPUT_ROOT, "allocated_resources": allocated_resources }


class RapidDiagInfoEndpoint(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        pass

    def handle(self, args):
        return persistent_handler_wrap_handle(self._handle, args)

    def _handle(self, args):
        local = next((arg[1] for arg in args['query'] if arg[0]=='local'), False)
        if not local:
            collector_availability_status = json.dumps(get_collector_availability_status(args['system_authtoken']))
        else:
            collector_availability_status = get_endpoint('rapid_diag/info', args['system_authtoken'])
        _LOGGER.debug("Response: " + str(collector_availability_status))
        return {'payload': collector_availability_status, 'status': 200}
