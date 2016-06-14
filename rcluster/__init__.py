__title__ = 'rcluster'
__ver__ = '0.2.2'

from .rcluster import RCluster
from .pmkutils import pmkGet, pmkPut, pmkWalk, pmkCmd, cpuCount, pmkConnect

# Add logging (defaults to null, but can be picked up by any logger)
import logging
from logging import NullHandler

logging.getLogger(__name__).addHandler(NullHandler())

import os

# Outputs will be saved to user's home directory in a hidden folder
_OUTDIR = os.path.join(os.path.expanduser('~'), '.rcluster')
os.makedirs(_OUTDIR, exist_ok=True)
# Stable identification of installation directory
_ROOT = os.path.abspath(os.path.dirname(__file__))


def setData(ext):
    return os.path.join(_OUTDIR, __ver__ + '.' + ext)


def getData(path):
    return os.path.join(_ROOT, 'data', path)
