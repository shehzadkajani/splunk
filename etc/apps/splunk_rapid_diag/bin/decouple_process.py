import os
import sys
import logger_manager as log

_LOGGER = log.setup_logging("decouple_process")

IS_LINUX = sys.platform.startswith('linux')

class DecoupleProcess(object):
    @staticmethod
    def create_independent_process():
        num_forks = 2
        # Double forking mechanism
        for i in range(num_forks):
            try:
                pid = os.fork()
                if pid > 0:
                    if i==0:
                        # first parent stays alive for any required cleanup and/or communication
                        return False
                    else:
                        # second parent leaves immediately
                        os._exit(0)
            except OSError as e:
                _LOGGER.exception("Error while creating process. " + str(e))
                sys.exit(1)

            os.chdir("/")
            os.setsid()
            os.umask(0)
        return True

    @staticmethod
    def run(functor):
        """
        Run `functor` decoupled of the original process (in supported platforms).
        Initial parent returns `False`, potentially decoupled child returns `True`, any others are mercilessly killed.
        If the platform doesn't support decoupling, the parent will run `functor` and return `False`.
        """
        if IS_LINUX:
            is_child = DecoupleProcess.create_independent_process()
            if not is_child:
                return False
        functor()
        return IS_LINUX
