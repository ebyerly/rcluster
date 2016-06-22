"""
:mod:`~rcluster.pmkutils` collects the functions used to interact with remote
AWS servers using :py:class:`paramiko.client.SSHClient` and
:py:class:`paramiko.sftp_client.SFTPClient` objects.
"""

import os
import stat
import paramiko
from time import sleep
from logging import getLogger


def pmkConnect(host, key_path, username='ubuntu'):
    """
    Create SSH connection to host, retrying on failure.

    :param host: The address of the remote server
    :param key_path: The location of the key pair file
    :param username: The username to access on the remote server
    """
    log = getLogger(__name__)
    log.debug('Connecting to %s@%s using key %s', username, host, key_path)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.client.AutoAddPolicy())
    try:
        log.debug('Connecting to host %s', host)
        k = paramiko.RSAKey.from_private_key_file(key_path)
        client.connect(hostname=host, username=username, pkey=k)
        return client
    except (TimeoutError, ConnectionRefusedError,
            paramiko.ssh_exception.NoValidConnectionsError) as err:
        log.debug('OS error: %s', err)
        sleep(15)
        return pmkConnect(host, key_path, username)
    except Exception as err:
        log.error('Connection failed, unexpected error:', err)
        raise err


def pmkCmd(client, call):
    """Issue command over SSH, treat execution failure as program failure.

    :param client: :py:class:`paramiko.client.SSHClient` class object
    :param call: String of shell command to be executed
    """
    log = getLogger(__name__)
    log.debug('Issuing "%s"', call)
    stdin, stdout, stderr = client.exec_command(call)
    lines = []
    for line in iter(lambda: stdout.readline(2048), ""):
        log.debug(line.encode('utf-8'))
        lines += line
    exit_status = stdout.channel.recv_exit_status()
    if exit_status:
        text = ''.join(stderr.readlines()).encode('utf-8')
        log.error(text)
        raise Exception(text)
    return lines


def cpuCount(client):
    """
    Given a :py:class:`paramiko.client.SSHClient` object, return the remote's
    CPU count
    """
    cpus = pmkCmd(client, r'cat /proc/cpuinfo | grep processor | wc -l')
    cpus = int(cpus[0])  # original format: ['2', '\n']
    return cpus


def _unixJoin(left, right):
    return left + "/" + right


def _unixPath(fn):
    return fn.replace("\\", "/")


def pmkPut(client, source, target):
    """
    Copy local files to remote target. Directories are copied recursively when
    provided as the source. Will do nothing if source does not exist.

    :param client: :py:class:`paramiko.client.SSHClient` object
    :param source: The local data source
    :param target: The remote data destination
    """
    sftp_conn = client.open_sftp()
    if os.path.isdir(source):
        for root, dirs, files in os.walk(source):
            for file in files:
                orig = _unixJoin(root, file)
                fn = os.path.relpath(orig, source)
                dest = _unixPath(_unixJoin(target, fn))
                try:
                    sftp_conn.mkdir(os.path.dirname(dest))
                except OSError:
                    pass
                sftp_conn.put(orig, dest)
    elif os.path.isfile(source):
        try:
            sftp_conn.mkdir(os.path.split(target)[0])
        except OSError:
            pass
        sftp_conn.put(source, target)


def pmkWalk(sftp_conn, dir):
    """paramiko os.walk() equivalent.

    :param sftp_conn: :py:class:`paramiko.sftp_client.SFTPClient` object
    :param dir: Remote directory targeted
    """
    path = dir
    files = []
    folders = []
    for f in sftp_conn.listdir_attr(dir):
        if stat.S_ISDIR(f.st_mode):
            folders.append(f.filename)
        else:
            files.append(f.filename)
    yield path, folders, files
    for folder in folders:
        for x in pmkWalk(sftp_conn, _unixJoin(dir, folder)):
            yield x


def pmkGet(client, source, target):
    """
    Copy remote files to a local target directory.

    If the source path is a directory, the directory will be copied recursively.
    If the source path is a file, the single file will be copied.

    :param client: :py:class:`paramiko.client.SSHClient` object
    :param source: The remote data source (directory or file)
    :param target: A local folder
    """
    sftp_conn = client.open_sftp()
    sftp_conn.chdir(os.path.split(source)[0])
    parent = os.path.split(source)[1]
    if stat.S_ISDIR(sftp_conn.lstat(parent).st_mode):
        for path, folders, files in pmkWalk(sftp_conn, parent):
            tdir = os.path.join(target, path)
            os.makedirs(tdir, exist_ok=True)
            for file in files:
                sftp_conn.get(_unixJoin(path, file), os.path.join(tdir, file))
    else:
        sftp_conn.get(parent, os.path.join(target, parent))
