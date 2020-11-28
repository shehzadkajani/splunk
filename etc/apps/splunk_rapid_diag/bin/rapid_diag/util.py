# python imports
from __future__ import absolute_import
import os
import sys
import subprocess
import datetime
import json
import time
import math
import getpass 
from functools import wraps

# local imports
from rapid_diag.serializable import Serializable

# splunk imports
from splunk import entity
from splunk.rest import simpleRequest


BUILD_FORMAT = "%Y-%m-%dT%Hh%Mm%Ss%fus"
IS_LINUX = sys.platform.startswith('linux')


SERVER_NAME = None
def get_server_name(session_key):
    global SERVER_NAME
    if SERVER_NAME is not None:
        return SERVER_NAME
    uri = entity.buildEndpoint(['server', 'info'])
    header, body = simpleRequest(uri, method='GET', getargs={'output_mode':'json'}, sessionKey=session_key)
    info = json.loads(body)
    content = info['entry'][0]['content']
    SERVER_NAME = content.get('serverName')
    return SERVER_NAME

def flatten_collectors(collectors):
    collectors_found = []
    for collector in collectors:
        collector.apply_to_self(lambda collector, depth: collectors_found.append(collector))
    return collectors_found

def build_rapid_diag_timestamp(when=None):
    if when is None:
        when = datetime.datetime.utcnow()
    return when.strftime(BUILD_FORMAT)

def remove_empty_directories(path, remove_root=True):
    for root, dirs, files in os.walk(path, topdown=False):
        for name in dirs:
            dir_path = os.path.join(root, name)
            try:
                if time.time() - os.stat(dir_path).st_mtime > 600:
                    os.rmdir(dir_path)
            except:
                pass

    if remove_root and os.path.exists(path) and len(os.listdir(path)) == 0:
        os.rmdir(path)

def get_splunkhome_path(parts):
    """
    This method will try to import the `make_splunkhome_path` function.
    """
    try:
        from splunk.clilib.bundle_paths import make_splunkhome_path
        return make_splunkhome_path(parts)
    except ImportError:
        raise Exception("Error importing make_splunkhome_path from clilib, splunk version should be 8+")

def get_log_files():
    base_path = get_splunkhome_path(['var', 'log', 'splunk'])
    files = [f for f in os.listdir(base_path) if os.path.isfile(os.path.join(base_path, f)) and f.endswith(".log")]
    return sorted(files)


def getConfStanza(confName, stanzaName):
    try:
        from splunk.clilib.cli_common import getConfStanza
        return getConfStanza(confName, stanzaName)
    except ImportError:
        return None


def splunk_get_username():
    if sys.version_info[0] < 3:
        return raw_input("Splunk username: ")
    else:
        return input("Splunk username: ")

def splunk_login():
    try:
        import splunklib.client as client
        from splunklib.client import AuthenticationError

        s  = client.Service(username=splunk_get_username(), password=getpass.getpass())
        s.login()
        return s.token

    except Exception:
        return None

def getAppConf(confName, app, use_btool=True, app_path=None):
    try:
        from splunk.clilib.cli_common import getAppConf
        return getAppConf(confName, app, use_btool, app_path)
    except ImportError:
        raise Exception("Error importing getAppConf from clilib, splunk version should be 8+")


def get_json_validated(json_data):
    try:
        json.loads(json_data, object_hook=Serializable.jsonDecode)
        return {"valid": True, "reason": None}
    except KeyError as e:
        return { "valid": False, "reason": str(e) + " : Key required"}
    except TypeError as e:
        return { "valid": False, "reason": str(e)}
    except ValueError as e:
        return { "valid": False, "reason": str(e)}


def is_ptrace_allowed():
    if IS_LINUX:
        try:
            command = ['sysctl', '-n', 'kernel.yama.ptrace_scope']
            output = subprocess.check_output(command)
            x = output.strip()
            if isinstance(x, (bytes)):
                x = x.decode("utf-8")
            # make sure ptrace is set to 0 as we want to attach processes to it
            if x == '0':
                return [True, ""]
            return [False, "PTRACE is not allowed - cannot collect data. Make sure sysctl settings of kernel.yama.ptrace_scope is 0."
                    " Current value: %s."%(x)]
        except:
            return [True, "Not able to read kernel.yama.ptrace_scope value"]
    return [True, ""]


def bytes_to_str(msg):
    """decodes the bytes string to unicode string

    Parameters
    ----------
    msg : [str, bytes]
        data in str or bytes

    Raises
    ------
    UnicodeError
        if data is already decoded

    Returns
    -------
    [str]
        message string
    """
    if isinstance(msg, bytes):
        try:
            return msg.decode()
        except UnicodeError:
            return ""
    return msg


def str_to_bytes(msg):
    """encodes the bytes string to unicode string

    Parameters
    ----------
    msg : [str, bytes]
        data in str or unicode

    Raises
    ------
    TypeError
        if data is already encoded

    Returns
    -------
    [str]
        byte string
    """
    if isinstance(msg, str):
        try:
            return msg.encode('utf-8')
        except TypeError:
            return ""
    return msg


def retry(ExceptionToCheck, tries=3, delay=0.5, backoff=2, logger=None):
    """Retry calling the decorated function using an exponential backoff.

    Parameters
    ----------
    ExceptionToCheck : Exception or tuple
        the exception to check. may be a tuple of exceptions to check
    tries : int, optional
        number of times to try (not retry) before giving up, by default 3
    delay : float, optional
        initial delay between retries in seconds, by default 0.5
    backoff : int, optional
        backoff multiplier e.g. value of 2 will double the delay
        each retry, by default 2
    logger : Logger instance, optional
        logger to use, by default None

    Raises
    ------
    ValueError
        In case of invalid values for tries, delays and backoff.
    """
    if backoff <= 1:
        raise ValueError("backoff must be greater than 1")

    tries = math.floor(tries)
    if tries < 0:
        raise ValueError("tries must be 0 or greater")

    if delay <= 0:
        raise ValueError("delay must be greater than 0")

    def deco_retry(func):
        @wraps(func)
        def func_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return func(*args, **kwargs)
                except ExceptionToCheck as e:
                    msg = "%s, Retrying in %.1f seconds..." % (str(e), mdelay)
                    if logger:
                        logger.warning(msg)
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return func(*args, **kwargs)
        return func_retry
    return deco_retry

def get_templates_path():
    """This function for now returns path relative to SPLUNK_HOME.
    Should be moved to conf settings at some point - for now mostly to provide a way to mock in tests.
    """
    return get_splunkhome_path(
    ["etc", "apps", "splunk_rapid_diag", "SampleTasks"])
