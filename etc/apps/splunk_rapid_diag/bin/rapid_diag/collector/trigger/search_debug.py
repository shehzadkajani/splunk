# python imports
from __future__ import print_function, absolute_import
import re
import os
import csv
import sys
import glob
import time
import threading
from shutil import copy2, copyfileobj, move
import gzip

# if trigger is ran from CLI
SPLUNK_HOME = os.environ.get('SPLUNK_HOME')
SPLUNK_DB = os.environ.get('SPLUNK_DB')
if not SPLUNK_HOME or not SPLUNK_DB:
    print('ERROR: SPLUNK_HOME and SPLUNK_DB must be set in environment path.\nExecute the file via Splunk\'s python e.g $SPLUNK_HOME/bin/splunk cmd python <file_name.py>', file=sys.stderr)
    exit(1)
sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))))))

# local imports
from splunklib import six
import logger_manager as log
from rapid_diag.collector.trigger.trigger import Trigger
from rapid_diag.collector.trigger.monitored_file import MonitoredFile
from rapid_diag.collector.type import Type
from rapid_diag.collector.collector import Collector
from rapid_diag.collector.threadpool import ThreadPool
from rapid_diag.collector.collector_result import CollectorResult, AggregatedCollectorResult
from rapid_diag.util import get_splunkhome_path, flatten_collectors, build_rapid_diag_timestamp
from rapid_diag.serializable import Serializable
from rapid_diag.session_globals import SessionGlobals
from rapid_diag.process_abstraction import ProcessLister, ProcessNotFound


_LOGGER = log.setup_logging("search_debug_trigger")


class FileNotFoundException(Exception):
    pass


class SearchDebug(Trigger, Serializable):
    """Search Debug Trigger waits on the splunk search that matches the regex.
    Upon finding the matching search configured collectors will start,
    along with that the search.log of the matched search and other non-sensitive files
    will be preserved in the output directory.

    Parameters
    ----------
    search_regex : str
        regular expression to match the search
    collectors : list
        list of collectors to run after search is found
    """
    def __init__(self, search_regex, collectors=None, state=Collector.State.WAITING):
        Trigger.__init__(self)
        self.search_regex = search_regex
        self.collectors = collectors if collectors is not None else []
        self.state = state
        # this separate thread pool is used to queue log files preservation using one thread only to avoid additional queueing implementation.
        self.threadpool = ThreadPool(soft_limit=1, hard_limit=1)

    def _collect_impl(self, run_context):
        """Search Debug trigger waiting for the search to start.
        This method monitors the dispatch folder, until the regex is matched with search.
        User has to manually start the search for now.
        In future, historical search data of splunk will be used to select the searches to target.

        Parameters
        ----------
        run_context : object
            object of RunContext class
        """
        _LOGGER.info('Starting search debug collection with regular expression=' + str(self.search_regex))
        _LOGGER.debug("Task assigned to thread: " + str(threading.current_thread().name))
        _LOGGER.debug("ID of process running task: " + str(os.getpid()))

        dispatch_path = get_splunkhome_path(['var', 'run', 'splunk', 'dispatch'])
        visited_dirs = set()

        while True:
            try:
                # keeping track of visited dispatch directories so that we can avoid already seen ones
                dispatch = glob.glob(os.path.join(dispatch_path, '*'))
                dispatch = [directory for directory in dispatch if directory not in visited_dirs]
                curContext = run_context.clone()
                curContext.suffix = '_' + build_rapid_diag_timestamp()
                for dispatch_dir in dispatch:
                    sid = os.path.basename(dispatch_dir)
                    _LOGGER.info("Exploring " + dispatch_dir)
                    try:
                        # rsa -> replicated search artifacts
                        # searches are replicated on cluster members
                        # search results will be replicated on cluster members
                        # checked directory name to avoid matching rsa search directories
                        if sid.startswith("rsa_"):
                            visited_dirs.update(dispatch)
                            continue

                        info_file = os.path.join(dispatch_dir, 'info.csv')
                        with open(info_file, "r") as f:
                            reader = csv.DictReader(f)
                            search_info = next(reader)
                        if "/rapid_diag/" in search_info["_search"]:
                            visited_dirs.update(dispatch)
                        elif re.search(self.search_regex, search_info["_search"]):
                            # not using splunkd.pid file as it is not present on windows
                            # as we are caching the process list, process may not appear immediately
                            # going to find another way to check the process
                            # not using status.csv as it will not present on cluster members
                            pl = SessionGlobals.get_process_lister()
                            for process in pl.get_process_listing(True):
                                try:
                                    if process.process.process_type == 'splunk search' and '--id='+sid in process.process.args:
                                        self.promote_state(Collector.State.COLLECTING, curContext.stateChangeObservers)
                                        _LOGGER.info("Regex matched with the search dispatch directory " + str(dispatch_dir))
                                        return self._collect(dispatch_dir, process, curContext)
                                except AttributeError:
                                    pass
                                except ProcessNotFound:
                                    pass
                                except FileNotFoundException:
                                    continue
                                except Exception as e:
                                    return CollectorResult.Exception(e, 'Error monitoring dispatch.\n', _LOGGER)
                            _LOGGER.info('Splunk search process not found because it was completed too early.')
                        else:
                            visited_dirs.update(dispatch)
                    except Exception as e:
                        _LOGGER.info("Skipping dir='" + sid + "' reason='" + str(e) + "'")
                        continue

                time.sleep(0.2)

            except Exception as e:
                return CollectorResult.Exception(e, 'Error monitoring dispatch.\n', _LOGGER)
            finally:
                if self.get_state() == Collector.State.ABORTING:
                    return CollectorResult.Aborted('Search Debug trigger aborted by user', _LOGGER)

    def _collect(self, dispatch_dir, process, run_context):
        """Once the search is matched collectors configured will start gathering data.
        We are also preserving all the search.log along with running the collectors,
        because sid folders are volatile.
        
        For preservation, we are creating an empty file named `save` in dispatch directory
        this prevents splunk from deleting the that directory.
        Once `search.log` file starts rotating, we rename them locally and archive them to .gz file.
        Later after the search has finished, we move all gzipped search.log files to our task output directory.
        At last the non-sensitive files are copied over to the output directory.

        Parameters
        ----------
        dispatch_dir: str
            search dispatch directory path
        process: object
            object of Process or SearchProcess class
        run_context : RunContext
            object of RunContext class

        Returns
        -------
        AggregatedCollectorResult
            contains Collector Result object with updated status

        """
        result = AggregatedCollectorResult()
        tokens = []

        # filtering out the collectors whose resources are not available
        self.filter_collectors()

        # if SystemCallTrace and StackTrace collectors are there,
        # then update their process attribute with the found search process

        for collector in flatten_collectors(self.collectors):
            try:
                if collector.process.process:
                    collector.process = process if (collector.process.process.pid == 0 and collector.process.process.args.startswith("this is just a dummy process")) else collector.process
            except AttributeError:
                pass

        for collector in self.collectors:
            tokens.append(SessionGlobals.get_threadpool().add_task(collector.collect, run_context))

        try:
            try:
                # creating file named `save` to dispatch directory to stop splunk from deleting it
                # this will allow us to move the search.log files later to data collection directory
                open(os.path.join(dispatch_dir, 'save'), 'w').close()
            except Exception as e:
                raise FileNotFoundException()

            known_uids = set()
            latest_log_path = os.path.join(dispatch_dir, 'search.log')
            old_log_path = latest_log_path+'.[0-9]'

            # preserve the log files until the search process has not finished
            # or abort is called on the trigger
            tracked_process = ProcessLister.build_process_from_pid(process.get_pid())
            while self.get_state() != Collector.State.ABORTING and tracked_process \
                and hasattr(tracked_process, 'process') \
                and tracked_process.process.process_type == 'splunk search' \
                and '--id='+os.path.basename(dispatch_dir) in tracked_process.process.args:
                # periodically preserve old log files
                for file_path in glob.glob(old_log_path):
                    self._preserve(known_uids, file_path)
                time.sleep(0.2)
                tracked_process = ProcessLister.build_process_from_pid(process.get_pid())

        except ProcessNotFound:
            _LOGGER.debug("Search process " + str(process) + " has terminated.")

        except Exception as e:
            _LOGGER.error("Error preserving the dispatch directory files: " + str(e))

        except:
            _LOGGER.exception("Unknown Error!")

        # preserve files missed between sleep time and search process termination
        # and at last preserve the search.log file
        for path in (old_log_path, latest_log_path):
            for file_path in glob.glob(path):
                self._preserve(known_uids, file_path)

        # join the archiving thread
        try:
            self.token.wait()
            _LOGGER.debug("Successfully terminated the archiving thread.")
        except:
            pass

        output_dispatch_path = os.path.join(run_context.outputDir, "dispatch", os.path.basename(dispatch_dir))
        if not os.path.isdir(output_dispatch_path):
            try:
                os.makedirs(output_dispatch_path)
            except OSError as e:
                _LOGGER.debug("While creating " + output_dispatch_path + ": " + str(e))
        # move the archived gzip log files
        for gz in glob.glob(os.path.join(dispatch_dir, 'search.log.*.gz')):
            try:
                move(gz, os.path.join(output_dispatch_path, os.path.basename(gz)))
            except Exception as e:
                _LOGGER.error("Skipping file " + str(gz) + ": " + str(e))
        self._copy_other_files(dispatch_dir, output_dispatch_path)

        try:
            # delete the created `save` file from dispatch dir
            os.remove(os.path.join(dispatch_dir, 'save'))
        except:
            pass

        # waiting on collectors to finish data collection
        for token in tokens:
            token.wait()
            result.addResult(token.get_result())

        # yeah so if we just had empty collectors - no resource conflicts - we return success
        if not self.collectors and not self.conflicts:
            return CollectorResult.Success("No collectors to execute - returning search artefacts only.")
        return CollectorResult.Failure("All resources are occupied, could not start any of the collectors.\
            Only gathering search dispatch directory data.") if (not self.collectors) and self.conflicts else result

    def _preserve(self, known_uids, file_path):
        """Rename the search.log.[0-9] files locally in the dispatch directory.
        Files are only renamed if it was not seen previously.
        File UID is used to keep track of already visited files.

        NOTE: Rename is used instead of directly copying them to output directory,
        because former is faster than later.
        
        Parameters
        ----------
        known_uids : list
            list of file uids, inode in case of linux and
            unique file handle in case of windows
        file_path : str
            path of search.log.[0-9] file
        """
        try:    
            with MonitoredFile(file_path) as mon_file:
                if mon_file.uid not in known_uids:
                    _LOGGER.debug("Renaming file " + str(file_path) + " with uid " + str(mon_file.uid))
                    file_path_preserved = file_path + '.' + str(os.stat(file_path).st_mtime)
                    os.rename(file_path, file_path_preserved)
                    self.token = self.threadpool.add_task(self.gzip_file, file_path_preserved)
                    known_uids.add(mon_file.uid)
        except Exception as e:
            _LOGGER.error("Error preserving the dispatch directory files: " + str(e))

    def gzip_file(self, fname):
        """gzip the search log files as we go into separate .gz files.
        .gz is chosen for archiving because it is more splunk-like.
        Later removing the original file after archiving.
        NOTE: Only called for files which are not going to be written to anymore.
        
        Parameters
        ----------
        fname : str
            path to file
        """
        _LOGGER.debug("gzipping file: " + str(fname) + " in thread " + str(threading.current_thread().name))        
        try:
            with open(fname, 'rb') as f_in, gzip.open(fname +'.gz', 'wb') as f_out:
                _LOGGER.debug("Archiving file " + str(fname))
                copyfileobj(f_in, f_out)
            os.remove(fname)
        except Exception as e:
            _LOGGER.error("Error archiving the file " + str(fname) + ": " + str(e))

    def _copy_other_files(self, dispatch_dir, output_dir):
        """Copy the non-sensitive files from search dispatch directory to the task output directory.
        NOTE: Call this method only after the search has ended.

        Parameters
        ----------
        dispatch_dir : str
            path to search dispatch directory
        output_dir : str
            path to task output directory
        """
        # copy only files in the job's dir, skip all the .gz stuff
        for f in os.listdir(dispatch_dir):
            try:
                src_file = os.path.join(dispatch_dir, f)
                # don't capture the customer's data, or zero byte status indicator files.
                if f == "save" or f.endswith('.gz') or f.startswith('results') or f.endswith(".token"):
                    continue
                if os.path.isdir(src_file):
                    # don't collect subdirs, could be big, won't be informative.
                    continue
                copy2(src_file, os.path.join(output_dir, f))
            except Exception as e:
                _LOGGER.error("Skipping file " + str(f) + ": " + str(e))

    def getType(self):
        return Type.CONTINUOUS

    def __repr__(self):
        return "Search Debug(Search regex: %s)" % (self.search_regex)

    def toJsonObj(self):
        return {
            'search_regex': self.search_regex,
            'collectors': self.collectors,
            'state': Collector.State.get_status_string(self.state)
        }

    @staticmethod
    def validateJson(obj):
        data_types = {"search_regex": (six.text_type,), "collectors": (list,)}
        for field in list(filter(lambda x: x in obj.keys(), data_types.keys())):
            Serializable.check_data_type(obj[field], data_types[field], field)

    @staticmethod
    def fromJsonObj(obj):
        return SearchDebug(obj['search_regex'], obj['collectors'], Collector.State.get_status_code(obj.get("state")))

Serializable.register(SearchDebug)
