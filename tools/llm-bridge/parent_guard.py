"""Linux child exec guard; kill the model even if the bridge is SIGKILLed."""
import ctypes
import os
import signal
import sys

parent = int(sys.argv[1])
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
    raise OSError(ctypes.get_errno(), 'PR_SET_PDEATHSIG failed')
if os.getppid() != parent:
    raise SystemExit('Parent already exited')
os.execv(sys.argv[2], sys.argv[2:])
