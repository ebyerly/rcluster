"""
:mod:`rcluster.__exec__` provides command line utilities for using basic
:class:`.rcluster.RCluster` features:

* Populate a configuration file with your AWS access data
* Setup AWS to run an R cluster
* Launch an R cluster
* Access a running R cluster
* Terminate an R cluster
"""

import argparse
import webbrowser
import logging

import rcluster as rcl

parser = argparse.ArgumentParser()
parser.add_argument('-d', '--debug', help="Print lots of debugging statements",
                    action="store_const", dest="loglevel", const=logging.DEBUG,
                    default=logging.WARNING)
parser.add_argument('-v', '--verbose', help="Be verbose",
                    action="store_const", dest="loglevel", const=logging.INFO)


def main():
    """Launch an RCluster using the information saved to a configuration file"""
    parser.add_argument('-w', '--workers', type=int, nargs=1, default=[1],
                        help='The number of workers to launch.')
    parser.add_argument('-t', '--type', type=str, nargs=1, default='m4.large',
                        help='The instance type to use.')
    parser.add_argument('-c', '--config', type=str, nargs=1,
                        default=rcl._setData('json'),
                        help='The JSON RCluster configuration file.')
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel)
    log = logging.getLogger()

    try:
        cluster = rcl.RCluster.fromConfig(args.config)
    except FileNotFoundError as err:
        log.err('Run `rcluster-config`, first, to generate your own config',
                'file with the minimum necessary data to start an R cluster.')
        raise err
    ip = cluster.retrieveAccessIp()
    if ip:
        log.info("Active rcluster found.\n",
                 "Run `rcluster-terminate` to remove the previous cluster.\n"
                 "Returning current master instance.\n")
    else:
        cluster.createCluster(args.workers[0], InstanceType=args.type)
        ip = cluster.access_ip
    _openIp(ip)
    cl_data = ('Master IP Address:', ip)
    log.info(cl_data)
    term = ''
    while term not in 'yn':
        term = input("""
        Type 'y' to terminate the cluster and exit.
        Type 'n' to exit without terminating the cluster.
        You can always terminate your current RCluster by running
        `rcluster-terminate` from the command line.
        """)
    if term == 'y':
        cluster.terminateInstances()


def config():
    """
    Configure RCluster and AWS EC2 account.
    Prompts user for credentials, builds an AMI with specified R packages
    installed, and saves out the configuration file with credentials to a hidden
    folder in the user's home directory.
    """
    import shutil
    parser.add_argument('-o', '--outfile', type=str, nargs=1,
                        default=rcl._setData('json'),
                        help='The file in which to save the RCluster' +
                             'configuration data (stored in JSON format)')
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel)

    setup_cl = rcl.RCluster.fromConfig(rcl._getData('config.json'), purge=True)
    setup_cl.writeConfig(args.outfile)
    setup_script = shutil.copyfile(rcl._getData('ami.sh'), rcl._setData('sh'))
    # TODO: validate inputs
    pswd = input("Enter `cluster` user password: ")
    pkgs = input("Enter R packages to install (in format: `dplyr,plyr,etc`): ")
    pkgs = '"' + '", "'.join(pkgs.split(",")) + '"'
    with open(setup_script, 'a', newline='') as script:
        script.write('echo "cluster:{0}" | chpasswd\n'.format(pswd))
        script.write(("R --vanilla -q -e 'install.packages(c({0}), repo = "
                      "\"https://cran.cnr.berkeley.edu/\")'\n").format(pkgs))
    setup_cl.createAmi(setup_fn=setup_script)
    setup_cl.writeConfig(args.outfile)


def terminate():
    """
    Terminate all AWS instances associated with the specified RCluster
    configuration file.
    """
    parser.add_argument('-c', '--config', type=str, nargs=1,
                        default=rcl._setData('json'),
                        help='The JSON RCluster configuration file.')
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel)

    cluster = rcl.RCluster.fromConfig(args.config)
    cluster.terminateInstances()


def retrieveCluster():
    """
    Retrieve the access IP address of the current master instance (if live).
    Also opens a 
    """
    parser.add_argument('-c', '--config', type=str, nargs=1,
                        default=rcl._setData('json'),
                        help='The JSON RCluster configuration file.')
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel)
    log = logging.getLogger()

    cluster = rcl.RCluster.fromConfig(args.config)
    ip = cluster.retrieveAccessIp()
    if ip:
        log.debug(ip)
        _openIp(ip)


def _openIp(ip):
    """Open a browser pointed to an IP address's 8787 port"""
    webbrowser.open('http://' + ip + ":8787/")
