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

_LOGGER = log.setup_logging("task_abort_endpoint")


class TaskAbortEndpoint(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        pass

    def handle(self, args):
        return persistent_handler_wrap_handle(self._handle, args)

    def _handle(self, args):
        task_id = next((arg[1] for arg in args['query'] if arg[0]=='task_id'), '')
        local = next((arg[1] for arg in args['query'] if arg[0]=='local'), False)
        current_host = get_server_name(args['system_authtoken'])
        success = {'payload': json.dumps({"message": "Started aborting the Task with ID: " + str(task_id) + "."}),
                              'status': 200}
        if not local:
            handler = TaskHandler()
            tasks = handler.list(current_host)
            for task in tasks:
                if task_id == task["task"]["task_id"] and current_host == task["task"]["host"]:
                    task_handler = TaskHandler()
                    task_handler.abort(json.dumps(task))
                    return success
            return {'payload': json.dumps({"error": "Task not found."}), 'status': 404}

        host = next((arg[1] for arg in args['query'] if arg[0]=='host'), 'local')
        service = client.connect(host=splunk.getDefault('host'),
                                port=splunk.getDefault('port'),
                                scheme=splunk.getDefault('protocol'),
                                token=args['system_authtoken'])
        kwargs_normalsearch = {"exec_mode": "normal"}
        rest_search = '| rest /services/rapid_diag/task_abort count=0 task_id="' + task_id + '"'

        if host != current_host: # Abort the task only on the selected peer
            rest_search += ' splunk_server="' + host + '"'

        service.jobs.create(rest_search, **kwargs_normalsearch)
        return success

