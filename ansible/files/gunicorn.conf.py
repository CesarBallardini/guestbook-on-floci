"""gunicorn's settings on the instance, beyond its command line in supervisord.conf.

One rule: a worker dies with its master. Without it, when the master is killed outright
(SIGKILL, the kernel out of memory) its workers live on and keep the port, and the master
that supervisord starts next can never bind it.
"""

import ctypes
import signal

# From <sys/prctl.h>: the signal a process gets when its parent dies.
PR_SET_PDEATHSIG = 1


def post_fork(server, worker):
    """In each new worker: ask the kernel for SIGTERM when the master dies."""
    ctypes.CDLL(None, use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
