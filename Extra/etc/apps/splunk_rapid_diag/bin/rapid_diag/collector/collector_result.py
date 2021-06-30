class CollectorResult(object):
    SUCCESS = 0
    PARTIAL_SUCCESS = 1
    FAILURE = 2
    ABORTED = 3
    STATUS_STRINGS = {
        'Success': SUCCESS,
        'Partial Success': PARTIAL_SUCCESS,
        'Failure': FAILURE,
        'Aborted': ABORTED
    }

    def __init__(self, status=None, message=None, logger=None, exception=None):
        self.status = status
        if logger is not None and message is not None:
            logFunc = logger.info
            except_str = ''
            if status not in [CollectorResult.SUCCESS, CollectorResult.ABORTED]:
                logFunc = logger.error
                if exception is not None:
                    logFunc = logger.exception
                    except_str = ' exception: ' + str(exception)
            # TODO maybe store message in the future so we can display all or some of it in the UI?
            logFunc(message + except_str)

    @staticmethod
    def isValid(state):
        return state in CollectorResult.STATUS_STRINGS.values()

    @staticmethod
    def Success(message=None, logger=None):
        return CollectorResult(CollectorResult.SUCCESS, message, logger)

    @staticmethod
    def Failure(message=None, logger=None):
        return CollectorResult(CollectorResult.FAILURE, message, logger)

    @staticmethod
    def Exception(exception=None, message=None, logger=None):
        return CollectorResult(CollectorResult.FAILURE, message, logger, exception)

    @staticmethod
    def Aborted(message=None, logger=None, exception=None):
        return CollectorResult(CollectorResult.ABORTED, message, logger, exception)

    def isSuccess(self):
        return self.status==CollectorResult.SUCCESS

    def isFailure(self):
        return self.status==CollectorResult.FAILURE

    def isPartialSuccess(self):
        return self.status==CollectorResult.PARTIAL_SUCCESS

    def isAborted(self):
        return self.status==CollectorResult.ABORTED

    def getStatusString(self):
        return [key for key, value in CollectorResult.STATUS_STRINGS.items() if value == self.status][0]


class AggregatedCollectorResult(CollectorResult):
    def __init__(self):
        self.status = None

    # TODO consider getting token instead, and storing result and task info for better reporting
    def addResult(self, result):
        if self.status is None:
            self.status = result.status
        elif self.status!=result.status:
            if CollectorResult.ABORTED in {result.status, self.status}:
                self.status = CollectorResult.ABORTED
            else:
                self.status = CollectorResult.PARTIAL_SUCCESS
