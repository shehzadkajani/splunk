# python imports
import os
import sys
import json

# Reloading the rapid_diag bin path
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from splunk.persistconn.application import PersistentServerConnectionApplication

# local imports
import logger_manager as log
from splunklib.six.moves.urllib import parse
from rapid_diag_handler_utils import persistent_handler_wrap_handle
from rapid_diag.util import get_json_validated
from rapid_diag.collector.trigger import *
from rapid_diag.collector import *
from rapid_diag import process_abstraction, task

_LOGGER = log.setup_logging("json_validation_endpoint")


class JsonValidationEndpoint(PersistentServerConnectionApplication):
    def __init__(self, command_line=None, command_arg=None):
        pass

    def handle(self, args):
        return persistent_handler_wrap_handle(self._handle, args)

    def _handle(self, args):
        raw_json_data = next((arg[1] for arg in args['query'] if arg[0]=='payload'), '')
        json_data = json.loads(parse.unquote(raw_json_data))
        if 'task' in json_data:
            json_data = json_data['task']
        json_data = json.dumps(json_data)
        is_valid = get_json_validated(json_data)
        return {'payload': json.dumps({"valid": is_valid["valid"], "message": is_valid["reason"]}), 'status': 200}
