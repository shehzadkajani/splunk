from __future__ import absolute_import
import os
import io
import csv
import threading
from time import sleep

# local imports
import logger_manager as log
from rapid_diag.collector.type import Type
from rapid_diag.collector.collector import Collector
from rapid_diag.collector.collector_result import CollectorResult
from rapid_diag.serializable import Serializable

# splunk imports
import splunk
from splunklib import six
import splunklib.client as client
from splunklib.client import AuthenticationError
import splunklib.results as results

_LOGGER = log.setup_logging("search_result")
MAX_RETRIES = 3


class SearchResult(Collector, Serializable):
    """
    RapidDiag collector allows to collect search results.
    """

    def __init__(self, search_query=None, state=Collector.State.WAITING):
        Collector.__init__(self)
        self.search_query = search_query
        self.state = state

    def getType(self):
        return Type.CONTINUOUS

    def get_required_resources(self):
        return []

    def __repr__(self):
        return "Search Result(Search query: %s)\n" % (self.search_query)

    def toJsonObj(self):
        return {
            'search_query': self.search_query,
            'state': Collector.State.get_status_string(self.state)
        }

    @staticmethod
    def validateJson(obj):
        data_types = {"search_query": (six.text_type,)}
        for field in list(filter(lambda x: x in obj.keys(), data_types.keys())):
            Serializable.check_data_type(obj[field], data_types[field], field)

    @staticmethod
    def fromJsonObj(obj):
        return SearchResult(obj['search_query'], Collector.State.get_status_code(obj.get("state")))

    def _collect_impl(self, runContext):
        """collects search results based on provided query using Splunk Python SDK."""
        _LOGGER.info('Starting search result collector, outputDir="' + runContext.outputDir +
                     '" suffix="' + runContext.suffix + '" search_query="' + self.search_query + '"')
        _LOGGER.debug("Task assigned to thread: " +
                      str(threading.current_thread().name))
        fname = os.path.join(runContext.outputDir, 'search' + runContext.suffix + '.csv')
        job = None
        aborted_before_done = False
        retries = MAX_RETRIES

        # splunklib is having issue with auto-login flag: https://github.com/splunk/splunk-sdk-python/issues/219.
        # Due to this currently retrying doesn't help for re-connecting to logged in session.
        # As and when the issue will get fixed in splunklib, functionality will work properly.
        while retries > 0:
            try:
                service = client.connect(host=splunk.getDefault('host'),
                                        port=splunk.getDefault('port'),
                                        scheme=splunk.getDefault('protocol'),
                                        token=runContext.sessionToken,
                                        autologin=True)

                kwargs_export = {"output_mode": "csv", "exec_mode": "normal"}
                search_query = self.search_query
                if not self.search_query.lstrip().startswith('|'):
                    search_query = '| search ' + search_query
                job = service.jobs.create(search_query, **kwargs_export)

                # waiting till the job is ready
                while not job.is_ready():
                    pass

                while not job.is_done():
                    # finalizing the job, if collection is aborted before the job.is_done() returns True
                    # this way intermediate results can be stored
                    if self.get_state() == Collector.State.ABORTING:
                        aborted_before_done = True
                        job.finalize()
                        break
                    sleep(.2)

                result_count = int(job["resultCount"])
                _LOGGER.debug("Result Count is " + str(result_count))

                if result_count == 0:
                    with open(fname, "w") as output_file:
                        output_file.write("No results found")
                    break      

                # writing the data fetched in batches, so as to not overload the system
                for offset in range(0, result_count, 1000):
                    with open(fname, "a") as output_file:
                        results = job.results(offset=offset, count=1000, output_mode='csv')
                        # generally job.is_done() returns True quickly
                        # most of the time is taken in retrieving and writing the results
                        # so if abort is called in between writing the results, we return
                        # checking aborted_before_done, so as to not return before writing
                        if not aborted_before_done and self.get_state() == Collector.State.ABORTING:
                            return CollectorResult.Aborted('Search Result collector aborted by user', _LOGGER)
                        header = results.readline().decode('utf-8')
                        if offset == 0:
                            output_file.write(header)
                        output_file.write(results.read().decode('utf-8'))
                break

            except AuthenticationError:
                retries -= 1
                if retries == 0:
                    return CollectorResult.Failure('Request failed: Session is not logged in', _LOGGER)
                sleep(.2)
                _LOGGER.info("Session expired. Retrying to login")
            except ConnectionError:
                _LOGGER.info("Connection reset by peer")
            except Exception as e:
                if job is not None:
                    job.cancel()
                return CollectorResult.Exception(e, 'Error running search result collector', _LOGGER)
            finally:
                # returning if aborted between retries
                if self.get_state() == Collector.State.ABORTING:
                    return CollectorResult.Aborted('Search Result collector aborted by user', _LOGGER)

        return CollectorResult.Success('search result execution completed', _LOGGER)


Serializable.register(SearchResult)
