# python imports
import sys
import json
import logging
import logging.handlers

# splunk imports
from splunk.appserver.mrsparkle.lib import util as splunk_lib_util
from splunk import rest
from splunk import admin

# local imports
from rapid_diag.util import get_splunkhome_path, getAppConf

# taking log level from rapid_diag.conf located in default folder
# future scope add UI page to change log level
APP_NAME = "splunk_rapid_diag"


class GetSessionKey(admin.MConfigHandler):
    def __init__(self):
        self.session_key = self.getSessionKey()

def get_log_level():
    try:
        session_key_obj = GetSessionKey()
        session_key = session_key_obj.session_key
        if session_key is not None:
            _, content = rest.simpleRequest("/servicesNS/nobody/splunk_rapid_diag/configs/conf-rapid-diag", sessionKey=session_key, getargs={"output_mode": "json"}, raiseAllErrors=True)
            settings_data = json.loads(content)['entry']
            for i in range(len(settings_data)):
                data = settings_data[i].get('content')
                if data.get('log_level'):
                    return data.get('log_level').upper()
    except:
        conf_info = getAppConf('rapid_diag', APP_NAME)
        if conf_info and conf_info.get('logging'):
            return conf_info.get('logging').get('log_level')
    return logging.INFO

def setup_logging(name, use_stdout=False):
    '''
    Creates logger file with given file name and log level.

    :param log_name: Name of log file
    :param log_level: Log level
    :return: logger object
    '''

    # splunk_rapid_diag.log file will be stored at $SPLUNK_HOME/var/log/splunk folder
    logfile = get_splunkhome_path(["var", "log", "splunk", APP_NAME + '.log'])
    logger = logging.getLogger(name)
    logger.propagate = False
    log_level = get_log_level()
    logger.setLevel(log_level)

    handler_exists = any([True for h in logger.handlers
                          if h.baseFilename == logfile])
    # Rotating loggers if file size exceeds thresold
    if not handler_exists:
        file_handler = logging.handlers.RotatingFileHandler(logfile, mode="a",
                                                            maxBytes=10485760,
                                                            backupCount=10)
        stderr_handler = logging.StreamHandler(stream=sys.stderr)

        fmt_str = "%(asctime)s %(name)s %(levelname)s %(thread)d - %(message)s"
        console_fmt_str = "%(levelname)s: %(message)s"

        formatter = logging.Formatter(fmt_str)
        console_formatter = logging.Formatter(console_fmt_str)

        stderr_handler.setLevel(logging.ERROR)

        file_handler.setFormatter(formatter)
        stderr_handler.setFormatter(console_formatter)

        logger.addHandler(file_handler)
        logger.addHandler(stderr_handler)

        if log_level is not None:
            file_handler.setLevel(log_level)

        if use_stdout:
            stdout_handler = logging.StreamHandler(stream=sys.stdout)
            stdout_handler.setFormatter(logging.Formatter("%(message)s"))
            stdout_handler.setLevel(log_level)
            logger.addHandler(stdout_handler)

    return logger
