import os
import paramiko
from time import sleep

from logging import getLogger
log = getLogger(__name__)


def pmkConnect(host, key_path, username='ubuntu'):
    """
    Create SSH connection to host, retrying on failure.

    Keyword arguments:
    instance -- A boto3.EC2.Instance object
    """
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

    Keyword arguments:
    client -- paramiko.Client class object
    call -- String of shell command to be executed
    """
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
        raise text
    return lines


def cpuCount(client):
    """Given a paramiko.Client object, return the remote's CPU count"""
    cpus = pmkCmd(client, r'cat /proc/cpuinfo | grep processor | wc -l')
    cpus = int(cpus[0])  # original format: ['2', '\n']
    return cpus


def unixJoin(left, right): return left + "/" + right


def pmkPut(client, source, target):
    """
    Copy local files to remote target, copying directories recursively when
    provided as the source. Will do nothing if source does not exist.

    Keyword arguments:
    client -- paramiko.Client object
    source -- The local data source
    target -- The remote data destination
    """
    sftp_conn = client.open_sftp()
    if os.path.isdir(source):
        for root, dirs, files in os.walk(source):
            for file in files:
                orig = os.path.join(root, file)
                fn = os.path.relpath(orig, source)
                dest = unixJoin(target, fn)
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

    Keyword arguments:
    sftp_conn -- paramiko.sftp_client object
    dir -- Remote directory targeted
    """
    from stat import S_ISDIR
    path = dir
    files = []
    folders = []
    for f in sftp_conn.listdir_attr(dir):
        if S_ISDIR(f.st_mode):
            folders.append(f.filename)
        else:
            files.append(f.filename)
    yield path, folders, files
    for folder in folders:
        for x in pmkWalk(sftp_conn, unixJoin(dir, folder)):
            yield x


def pmkGet(client, source, target):
    """
    Copy remote files to local target. Currently configured to copy the entire
    content of directories.

    Keyword arguments:
    client -- paramiko.Client object
    source -- The remote data source
    target -- The local data destination
    """
    sftp_conn = client.open_sftp()
    sftp_conn.chdir(os.path.split(source)[0])
    parent = os.path.split(source)[1]
    os.makedirs(target, exist_ok=True)
    for path, folders, files in pmkWalk(sftp_conn, parent):
        os.makedirs(os.path.join(target, path), exist_ok=True)
        for file in files:
            sftp_conn.get(unixJoin(path, file), unixJoin(target, path))
