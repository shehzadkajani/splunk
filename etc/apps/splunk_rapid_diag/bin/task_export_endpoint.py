# python imports
import os
import sys
import json

# Reloading the rapid_diag bin path
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

# splunk imports
import splunk
from splunk.persistconn.application import PersistentServerConnectionApplication
import splunklib.client as client

# local imports
import logger_manager as log
from rapid_diag_handler_utils import persistent_handler_wrap_handle
from rapid_diag.task_handler import TaskHandler
from rapid_diag.util import get_server_name

_LOGGER = log.setup_logging("task_export_endpoint")


class TaskExportEndpoint(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        pass

    def handle(self, args):
        return persistent_handler_wrap_handle(self._handle, args)

    def _handle(self, args):
        task_id = next((arg[1] for arg in args['query'] if arg[0]=='task_id'), '')
        current_host = get_server_name(args['system_authtoken'])
        host = next((arg[1] for arg in args['query'] if arg[0]=='host'), current_host)

        handler = TaskHandler()
        tasks = handler.list(current_host)

        for task in tasks:
            if task_id == task["task"]["task_id"] and host == task["task"]["host"]:
                return {'payload': json.dumps(task, sort_keys=True, indent=4, separators=(',', ': ')),
                        'status': 200, 'headers': [("Content-Type", "application/json")]}

        return {'payload': json.dumps({"error": "Task not found"}), 'status': 404}


