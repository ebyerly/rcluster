import os
import logging

__title__ = 'rcluster'
__ver__ = '0.2.3'

# Add logging (defaults to null, but can be picked up by any logger)
logging.getLogger(__name__).addHandler(logging.NullHandler())

# Identify user's home directory, create hidden folder
_OUTDIR = os.path.join(os.path.expanduser('~'), '.rcluster')
os.makedirs(_OUTDIR, exist_ok=True)

# Identify location of rcluster installation
_ROOT = os.path.abspath(os.path.dirname(__file__))


def setData(ext):
    """Return path to save to hidden .rcluster folder in user directory"""
    return os.path.join(_OUTDIR, __ver__ + '.' + ext)


def getData(path):
    """Inputs are sourced from the rcluster installation directory"""
    return os.path.join(_ROOT, 'data', path)


from .rcluster import RCluster
from .pmkutils import pmkGet, pmkPut, pmkWalk, pmkCmd, cpuCount, pmkConnect
