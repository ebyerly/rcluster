"""
`rcluster` is a utility for configuring, launching, accessing, and managing R
clusters on AWS.

:class:`~.rcluster.RCluster` is the primary interface when used procedurally
within a Python script.

Command line tools include:

* ``rcluster-config`` (:func:`.__exec__.config`)
* ``rcluster`` (:func:`.__exec__.main`)
* ``rcluster-open`` (:func:`.__exec__.retrieve_cluster`)
* ``rcluster-terminate`` (:func:`.__exec__.terminate`)
"""

import os
import logging

__title__ = 'rcluster'
__ver__ = '0.2.21'

# Add logging (defaults to null, but can be picked up by any logger)
logging.getLogger(__name__).addHandler(logging.NullHandler())

# Identify user's home directory, create hidden folder
_OUTDIR = os.path.join(os.path.expanduser('~'), '.rcluster')
os.makedirs(_OUTDIR, exist_ok=True)

# Identify location of rcluster installation
_ROOT = os.path.abspath(os.path.dirname(__file__))


def _set_data(ext):
    """
    Return path to save a file to hidden ``.rcluster`` folder in user directory.

    :param ext: The extension to give the output file. (All outputs are given
        the same filename, based on the configuration version.)
    """
    return os.path.join(_OUTDIR, __ver__ + '.' + ext)


def _get_data(fn):
    """Inputs are sourced from the rcluster installation directory

    :param fn: The data file name to retrieve from the `rcluster` installation.
    """
    return os.path.join(_ROOT, 'data', fn)


from .rcluster import RCluster
from .pmkutils import pmk_connect, pmk_cmd, cpu_count, pmk_walk, \
    pmk_put, _pmk_put, pmk_get, _pmk_get
