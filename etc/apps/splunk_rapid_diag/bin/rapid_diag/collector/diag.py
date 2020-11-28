# python imports
from __future__ import print_function, absolute_import
import re
import os
import sys
import subprocess
import time
import shutil
import socket
from datetime import datetime
from distutils.version import LooseVersion

# if collector is ran from CLI
SPLUNK_HOME = os.environ.get('SPLUNK_HOME')
SPLUNK_DB = os.environ.get('SPLUNK_DB')
if not SPLUNK_HOME or not SPLUNK_DB:
    print('ERROR: SPLUNK_HOME and SPLUNK_DB must be set in environment path.\nExecute the file via Splunk\'s python e.g $SPLUNK_HOME/bin/splunk cmd python <file_name.py>', file=sys.stderr)
    exit(1)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))

# local imports
import logger_manager as log
from rapid_diag.collector.type import Type
from rapid_diag.collector.collector import Collector
from rapid_diag.collector.collector_result import CollectorResult
from rapid_diag.util import get_splunkhome_path, build_rapid_diag_timestamp, bytes_to_str
from rapid_diag.serializable import Serializable

_LOGGER = log.setup_logging("diag")


class Diag(Collector, Serializable):
    def __init__(self, state=Collector.State.WAITING):
        Collector.__init__(self)
        self.state = state

    def getType(self):
        return Type.SNAPSHOT

    def get_required_resources(self):
        return []

    def __repr__(self):
        return "Splunk Diag"

    def toJsonObj(self):
        return {'state': Collector.State.get_status_string(self.state)}

    @staticmethod
    def validateJson(obj):
        pass

    @staticmethod
    def fromJsonObj(obj):
        return Diag(Collector.State.get_status_code(obj.get("state")))

    def _get_splunk_version(self):
        version = '6.0'
        version_regex = re.compile(r'^Splunk\D+((?:\d+\.)+\d+)\b')
        try:
            res = subprocess.check_output([get_splunkhome_path(["bin", "splunk"]), '--version'], stderr=subprocess.STDOUT).decode('utf-8')
            match_result = version_regex.search(res)
            if match_result:
                version = match_result.group(1)
        except Exception as e:
            _LOGGER.error("Error getting splunk version, returning default 6.0 version.")
        return version

    def _collect_impl(self, runContext):
        self.promote_state(Collector.State.COLLECTING, runContext.stateChangeObservers)

        _LOGGER.info('Starting Diag collector, outputDir="' + runContext.outputDir + '" suffix="' + runContext.suffix + '"')
        fname = os.path.join(runContext.outputDir, 'diag' + runContext.suffix)
        command = [get_splunkhome_path(['bin', 'splunk']), 'diag', '--log-age=0']
        splunk_version = self._get_splunk_version()
        if LooseVersion(splunk_version) >= LooseVersion('6.4'):
            command += ['--nologin']
        if LooseVersion(splunk_version) >= LooseVersion('6.3'):
            command += ['--diag-name='+fname]
        if LooseVersion(splunk_version) >= LooseVersion('6.2'):
            command += ['--disable=rest']
        _LOGGER.debug('Running `' + ' '.join(command)+'`')

        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in range(1, 60*15):
                if process.poll() is not None:
                    break
                if self.get_state() == Collector.State.ABORTING:
                    try:
                        process.terminate()
                    except OSError:
                        pass
                    process.communicate()
                    return CollectorResult.Aborted('Splunk diag aborted by user', _LOGGER)
                time.sleep(1)
            else:
                try:
                    process.terminate()
                except OSError:
                    pass
                process.communicate()
                return CollectorResult.Failure('Splunk diag took too long, aborted process=' +
                                               ' '.join(command) + ' outputDir=' + runContext.outputDir + ' suffix=' + runContext.suffix,
                                               _LOGGER)
            out, err = process.communicate()  # returns bytes strings

            message = 'Process finished with code=' + str(process.returncode) + \
                      ' stdout="' + bytes_to_str(out) + '" stderr="' + bytes_to_str(err) + '"'
            if process.returncode != 0:
                return CollectorResult.Failure(message, _LOGGER)
            
            # moving the diag.tar.gz file to the corresponding task folder for splunk versions 6.0.x, 6.1.x and 6.2.x
            # as there is no option --diag-name in those versions of splunk diag
            if LooseVersion(splunk_version) < LooseVersion('6.3'):
                today = datetime.today().strftime('%Y-%m-%d')
                server_name = socket.gethostname()
                diag_file_name = 'diag-' + server_name + '-' + today + '.tar.gz'
                shutil.move(get_splunkhome_path([diag_file_name]), fname + '.tar.gz')

            return CollectorResult.Success(message, _LOGGER)
        except EnvironmentError as e:
            return CollectorResult.Exception(e, 'Error collecting splunk diag, process=' +
                                             ' '.join(command) + ' outputDir=' + runContext.outputDir + ' suffix=' + runContext.suffix,
                                             _LOGGER)
        except Exception as e:
            return CollectorResult.Exception(e, 'Error running splunk diag', _LOGGER)

 
Serializable.register(Diag)
