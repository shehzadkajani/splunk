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
from splunklib.binding import HTTPError

# local imports
import logger_manager as log
from rapid_diag_handler_utils import persistent_handler_wrap_handle
from rapid_diag.task_handler import TaskHandler
from decouple_process import DecoupleProcess
from rapid_diag.util import get_server_name

_LOGGER = log.setup_logging("task_rerun_endpoint")


class TaskRerunEndpoint(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        pass

    def handle(self, args):
        return persistent_handler_wrap_handle(self._handle, args)

    def _handle(self, args):
        current_host = get_server_name(args['system_authtoken'])
        task_id = next((arg[1] for arg in args['query'] if arg[0]=='task_id'), '')
        new_task_id = next((arg[1] for arg in args['query'] if arg[0]=='new_task_id'), '')
        success = {'payload': json.dumps({"message": "Task with ID " + str(task_id) + " has re-ran."}),
                   'status': 200}
        local = next((arg[1] for arg in args['query'] if arg[0]=='local'), False)
        host = next((arg[1] for arg in args['query'] if arg[0]=='host'), current_host)
        name = next((arg[1] for arg in args['query'] if arg[0]=='name'), '')
        handler = TaskHandler()
        if not local:
            try:
                tasks = handler.list(current_host)
                for task in tasks:
                    if task["task"]["task_id"] == task_id and task["task"]["host"] == current_host:
                        task["task"]["task_id"] = new_task_id
                        if DecoupleProcess.run(lambda: TaskHandler().create(json.dumps(task["task"]), args['system_authtoken'])):
                            os._exit(0) # due to persistent nature, child must exit successfully ASAP, parent will respond to server
            except Exception as exc:
                _LOGGER.error("Aborting: JSON decode error. Invalid JSON format or request body not found.\n{}" + str(exc))
                return {'payload': {"message": "JSON decode error. Invalid JSON format or request body not found."}, 'status': 401}
            return success

        new_task_id = TaskHandler.build_task_id(name, host)
        service = client.connect(host=splunk.getDefault('host'),
                                port=splunk.getDefault('port'),
                                scheme=splunk.getDefault('protocol'),
                                token=args['system_authtoken'])
        kwargs_normalsearch = {"exec_mode": "normal"}
        rest_search = '| rest /services/rapid_diag/task_rerun count=0 task_id="' + task_id + '" new_task_id="' + new_task_id + '"'
        if host != current_host: # Run the job only on peers
            rest_search += ' splunk_server="' + host + '"'
        service.jobs.create(rest_search, **kwargs_normalsearch)
        return success

