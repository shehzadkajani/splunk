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
from splunklib.six.moves.urllib import parse

# local imports
import logger_manager as log
from rapid_diag_handler_utils import persistent_handler_wrap_handle
from rapid_diag.task_handler import TaskHandler
from decouple_process import DecoupleProcess
from rapid_diag.util import get_server_name

_LOGGER = log.setup_logging("task_run_endpoint")


class TaskRunEndpoint(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        pass

    def handle(self, args):
        return persistent_handler_wrap_handle(self._handle, args)

    def _handle(self, args):
        task_body_string = None
        peers_string = None
        try:
            task_body_string = next((arg[1] for arg in args['query'] if arg[0]=='payload'), '')
            peers_string = next((arg[1] for arg in args['query'] if arg[0]=='peers'), '[]')
            peers = json.loads(peers_string)
            task_body = json.loads(parse.unquote(task_body_string))
            task_name = task_body.get('name', '')
            success = {'payload': json.dumps({"message": "Task " + task_name + " has started."}), 'status': 200}
        except Exception as exc:
            _LOGGER.exception("Aborting: JSON decode error. Invalid JSON format or request body not found: " + str(exc))
            return {'payload': json.dumps(
                {"message": "JSON decode error. Invalid JSON format or request body not found."}), 'status': 401}

        try:
            host = get_server_name(args['system_authtoken'])
            if not peers:
                if not task_body.get("host"):
                    task_body["host"] = host
                task_id = next((arg[1] for arg in args['query'] if arg[0]=='task_id'), TaskHandler.build_task_id(task_name, task_body["host"]))
                task_body.update({'task_id': task_id})
                task_body = json.dumps(task_body)

                if DecoupleProcess.run(lambda: TaskHandler().create(task_body, args['system_authtoken'])):
                    os._exit(0) # due to persistent nature, child must exit successfully ASAP, parent will respond to server
            else:
                task_id = TaskHandler.build_task_id(task_name, host)
                task_body = json.dumps(task_body)

                service = client.connect(host=splunk.getDefault('host'),
                                         port=splunk.getDefault('port'),
                                         scheme=splunk.getDefault('protocol'),
                                         token=args['system_authtoken'])
                kwargs_normalsearch = {"exec_mode": "normal"}
                for peer in peers:
                    rest_search = '| rest /services/rapid_diag/task_runner count=0 splunk_server="' + peer + '" payload="' + task_body_string + '" task_id="' + task_id + '"'
                    service.jobs.create(rest_search, **kwargs_normalsearch)
            return success
        except SystemExit as e:
            _LOGGER.exception("Error decoupling data collection process: " + str(e))
            return {'payload': json.dumps({"message": "Error starting up task collection process."}), 'status': 500}

