# python imports
import json

# splunk imports
import splunk

import splunklib.client as client
import splunklib.results as results
from splunklib.binding import HTTPError
import logger_manager as log
from rapid_diag.session_globals import SessionGlobals

# local imports
from rapid_diag.util import get_server_name
from rapid_diag.debug_utils import Profiler

API_VERSION = 1

_LOGGER = log.setup_logging("rapid_diag_handler_utils")


def get_endpoint(endpoint, session_key, peer=None):
    service = client.connect(host=splunk.getDefault('host'),
                             port=splunk.getDefault('port'),
                             scheme=splunk.getDefault('protocol'),
                             token=session_key)
    rest_search = '| rest /services/' + endpoint + ' count=0 max_api_version=' + str(API_VERSION)
    if peer:
        rest_search += ' splunk_server="' + peer + '"'
    else:
        rest_search += ' splunk_server=*'
    data = service.jobs.oneshot(rest_search)
    reader = results.ResultsReader(data)

    def _handle_info():
        data = []
        current_host = get_server_name(session_key)
        for item in reader:
            # always keeping originating SH value first
            idx = 0 if item.get("splunk_server","") == current_host else len(data)
            data.insert(idx, {"value": item.get("value", {}), "splunk_server": item.get("splunk_server","")})
        return data

    if endpoint.startswith("rapid_diag"):
        return _handle_info()
    return reader.next().get('value')


def persistent_handler_wrap_handle(handler, args, supported_methods=['GET']):
    with Profiler(_LOGGER) as prof:
        try:
            SessionGlobals.reset()
            args = json.loads(args)
        except Exception as e:
            _LOGGER.exception("Payload must be a json parseable string, JSON Object, or JSON List: " +
                              str(args) + ": " + str(e))
            return {'payload': json.dumps({"error": "Invalid request data."}), 'status': 400}
        if args.get('method') not in supported_methods:
            _LOGGER.exception("Request method must be in " + str(supported_methods) + ": " + str(args))
            return {'payload': json.dumps({"error": "Method Not Allowed: Request method must be in " +
                                                    str(supported_methods)}), 'status': 405}
        max_api_version = next((arg[1] for arg in args['query'] if arg[0] == 'max_api_version'), API_VERSION)
        if int(max_api_version) < API_VERSION:
            return {'payload': json.dumps({"error": "Unable to provide results for max_api_version=" +
                                                    str(max_api_version) + ", my_api_version=" +
                                                    str(API_VERSION) + " is higher."}), 'status': 404}
        
        def build_error_message(description, details):
            return description + args['rest_path'] + ': ' + details

        try:
            return handler(args)
        except SyntaxError as e:
            _LOGGER.exception("Syntax error:" + str(e), exc_info=e)
            return {'payload': json.dumps({
                "error": "You've found a bug! Very embarrassing, we're deeply sorry and would appreciate it if you " +
                         "could report it back to us: " + str(e)}), 'status': 503}
        except splunk.RESTException as e:
            msg = build_error_message('REST Error processing request to ', e.msg)
            _LOGGER.exception(msg, exc_info=e)
            return {'payload': json.dumps({'error': msg}), 'status': e.statusCode}
        except HTTPError as e:
            msg = build_error_message('HTTP Error processing request to ', e.reason)
            _LOGGER.exception(msg, exc_info=e)
            return {'payload': json.dumps({'error': msg}), 'status': e.status}
        except Exception as e:
            msg = build_error_message('Error processing request to ', str(e))
            _LOGGER.exception(msg, exc_info=e)
            return {'payload': json.dumps({"error": msg}), 'status': 500}

