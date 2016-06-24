"""
:mod:`~rcluster.pmkutils` collects the functions used to interact with remote
AWS servers using :py:class:`paramiko.client.SSHClient` and
:py:class:`paramiko.sftp_client.SFTPClient` objects.
"""
import os
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


def _unixPath(*args):
    """Most handle UNIX pathing, not vice versa, enforce standard"""
    return os.path.join(*args).replace('\\', '/')


def pmkWalk(sftp_conn, root):
    """paramiko os.walk() equivalent.

    :param sftp_conn: :py:class:`paramiko.sftp_client.SFTPClient` object
    :param dir: Remote directory targeted
    """
    import stat
    files = []
    dirs = []
    for f in sftp_conn.listdir_attr(root):
        if stat.S_ISDIR(f.st_mode):
            dirs.append(f.filename)
        else:
            files.append(f.filename)
    yield root, dirs, files
    for folder in dirs:
        for x in pmkWalk(sftp_conn, _unixPath(root, folder)):
            yield x


def _filesFromWalk(gen):
    """
    Talk a generator yielding root, dirs, files (as from os.walk()) and return a
    list of all files (with fully qualified paths).

    :param gen: Generator yielding root, dirs, files (as from os.walk())
    :type gen: generator
    :return:
    """
    all_files = []
    for root, dirs, files in gen:
        for fn in files:
            all_files.append(_unixPath(root, fn))
    return all_files


def pmkPut(client, sources, target, threaded=True):
    """
    Copy local files to remote target. Directories are copied recursively when
    provided as the source. Will do nothing if source does not exist.

    :param client: :py:class:`paramiko.client.SSHClient` object
    :param sources: The local data source
    :param target: The remote data destination
    """
    send_files = []
    if not type(sources) is list:
        sources = [sources]
    for source in sources:
        if os.path.isfile(source):
            target_fn = _unixPath(target, os.path.basename(source))
            send_files.append((source, target_fn))
        if os.path.isdir(source):
            for source_fn in _filesFromWalk(os.walk(source)):
                target_fn = _unixPath(target,
                                      os.path.relpath(source_fn, source))
                send_files.append((source_fn, target_fn))
    pmkPutFiles(client=client, send_files=send_files, threaded=threaded)


def pmkPutFile(client, source_fn, target_fn):
    from paramiko.ssh_exception import ChannelException
    from time import sleep
    log = getLogger(__name__)
    try:
        sftp_conn = client.open_sftp()
    except ChannelException as e:
        if 'Administratively prohibited' in str(e):
            sleep(1)
            pmkPutFile(client, source_fn, target_fn)
            return
        else:
            raise e
    try:
        sftp_conn.mkdir(os.path.dirname(target_fn))
    except OSError:
        pass
    log.debug("Sending %s to %s", source_fn, target_fn)
    sftp_conn.put(source_fn, target_fn)


def pmkPutFiles(client, send_files, threaded=True):
    if threaded:
        _thread_jobs(func=pmkPutFile, client=client, files=send_files)
    else:
        for source_fn, target_fn in send_files:
            pmkPutFile(client, source_fn, target_fn)


def pmkGet(client, sources, target, threaded=True):
    """
    Copy local files to remote target. Directories are copied recursively when
    provided as the source. Will do nothing if source does not exist.

    :param client: :py:class:`paramiko.client.SSHClient` object
    :param sources: The local data source
    :param target: The remote data destination
    """
    import stat
    sftp_conn = client.open_sftp()
    get_files = []
    if not type(sources) is list:
        sources = [sources]
    for source in sources:
        if stat.S_ISDIR(sftp_conn.lstat(source).st_mode):
            for source_fn in _filesFromWalk(pmkWalk(sftp_conn, source)):
                target_fn = os.path.join(target,
                                         os.path.relpath(source_fn, source))
                get_files.append((source_fn, target_fn))
        if os.path.isfile(source):
            get_files.append((source, target))
    pmkGetFiles(client, get_files, threaded=threaded)


def pmkGetFile(client, source_fn, target_fn):
    from paramiko.ssh_exception import ChannelException
    from time import sleep
    log = getLogger(__name__)
    try:
        sftp_conn = client.open_sftp()
    except ChannelException as e:
        if 'Administratively prohibited' in str(e):
            sleep(1)
            pmkGetFile(client, source_fn, target_fn)
            return
        else:
            raise e
    os.makedirs(os.path.dirname(target_fn), exist_ok=True)
    log.debug("Sending %s to %s", source_fn, target_fn)
    sftp_conn.get(source_fn, target_fn)


def pmkGetFiles(client, get_files, threaded=True):
    if threaded:
        _thread_jobs(func=pmkGetFile, client=client, files=get_files)
    else:
        for source_fn, target_fn in get_files:
            pmkGetFile(client, source_fn, target_fn)


def _thread_jobs(func, client, files):
    """
    An internal utility for threading put/get actions.

    :param files: A list containing two-tuples of (orig, dest)
    :type files: list
    :param func: Either sftp_conn.get or sftp_conn.put
    :type func: function
    :return:
    """
    from threading import Thread
    jobs = []
    for source_fn, target_fn in files:
        job = Thread(target=func, kwargs={"client": client,
                                          "source_fn": source_fn,
                                          "target_fn": target_fn})
        job.start()
        jobs.append(job)
    for job in jobs:
        job.join()
