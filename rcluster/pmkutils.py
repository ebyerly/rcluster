"""
:mod:`~rcluster.pmkutils` collects the functions used to interact with remote
AWS servers using :py:class:`paramiko.client.SSHClient` and
:py:class:`paramiko.sftp_client.SFTPClient` objects.
"""
import os
import stat
import paramiko
from time import sleep
from threading import Thread
from logging import getLogger


def _unix_path(*args):
    """Most handle UNIX pathing, not vice versa, enforce standard"""
    return os.path.join(*args).replace('\\', '/')


def _walk_files(gen):
    """
    Take a generator yielding root, dirs, files (as from os.walk()) and return a
    list of all files (with fully qualified paths).

    :param gen: Generator yielding root, dirs, files (as from os.walk())
    :type gen: generator
    :return:
    """
    all_files = []
    for root, dirs, files in gen:
        for fn in files:
            all_files.append(_unix_path(root, fn))
    return all_files


def _open_sftp(client):
    """
    Open and return. If connection denied due to too many active connections,
    try again recursively until successful.

    :param client:
    :return:
    """
    try:
        return client.open_sftp()
    except paramiko.ssh_exception.ChannelException as e:
        if 'Administratively prohibited' in str(e):
            sleep(1)
            return _open_sftp(client)
        else:
            raise e


def pmk_connect(host, key_path, username='ubuntu'):
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
        return pmk_connect(host, key_path, username)
    except Exception as err:
        log.error('Connection failed, unexpected error:', err)
        raise err


def pmk_cmd(client, call):
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


def cpu_count(client):
    """
    Given a :py:class:`paramiko.client.SSHClient` object, return the remote's
    CPU count. (
    """
    cpus = pmk_cmd(client, r'cat /proc/cpuinfo | grep processor | wc -l')
    cpus = int(cpus[0])  # original format: ['2', '\n']
    return cpus


def pmk_walk(sftp_conn, root):
    """paramiko os.walk() equivalent.

    :param sftp_conn: :py:class:`paramiko.sftp_client.SFTPClient` object
    :param root: Remote directory targeted
    """
    files = []
    dirs = []
    for f in sftp_conn.listdir_attr(root):
        if stat.S_ISDIR(f.st_mode):
            dirs.append(f.filename)
        else:
            files.append(f.filename)
    yield root, dirs, files
    for folder in dirs:
        for x in pmk_walk(sftp_conn, _unix_path(root, folder)):
            yield x


def _pmk_mover(func, client, file_tuples, threaded=True, thread_cap=10):
    """

    :param func:
    :param client:
    :param file_tuples:
    :param threaded:
    :return:
    """
    if threaded:
        jobs = []
        while len(file_tuples) > 0:
            if len(jobs) < thread_cap:
                source_fn, target_fn = file_tuples.pop()
                job = Thread(target=func, kwargs={"client": client,
                                                  "source_fn": source_fn,
                                                  "target_fn": target_fn})
                job.start()
                jobs.append(job)
            else:
                while len(jobs) >= thread_cap:
                    jobs = [job for job in jobs if job.is_alive()]
    else:
        for source_fn, target_fn in file_tuples:
            func(client, source_fn, target_fn)


def pmk_put(client, sources, target, threaded=True, thread_cap=10):
    """
    Copy local files to remote target. Directories are copied recursively when
    provided as the source. Will do nothing if source does not exist.

    :param client: :py:class:`paramiko.client.SSHClient` object
    :param sources: The local data source
    :param target: The remote data destination
    :param threaded:
    """
    send_files = []
    if not type(sources) is list:
        sources = [sources]
    for source in sources:
        if os.path.isfile(source):
            target_fn = _unix_path(target, os.path.basename(source))
            send_files.append((source, target_fn))
        if os.path.isdir(source):
            for source_fn in _walk_files(os.walk(source)):
                target_fn = _unix_path(target,
                                       os.path.relpath(source_fn, source))
                send_files.append((source_fn, target_fn))
    _pmk_mover(pmk_put_file, client=client, file_tuples=send_files,
               threaded=threaded, thread_cap=thread_cap)


def pmk_put_file(client, source_fn, target_fn):
    """

    :param client:
    :param source_fn:
    :param target_fn:
    :return:
    """
    log = getLogger(__name__)
    sftp_conn = _open_sftp(client)
    try:
        sftp_conn.mkdir(os.path.dirname(target_fn))
    except OSError:
        pass
    log.debug("Sending %s to %s", source_fn, target_fn)
    sftp_conn.put(source_fn, target_fn)
    sftp_conn.close()


def pmk_get(client, sources, target, threaded=True, thread_cap=10):
    """
    Copy local files to remote target. Directories are copied recursively when
    provided as the source. Will do nothing if source does not exist.

    :param client: :py:class:`paramiko.client.SSHClient` object
    :param sources: The local data source
    :param target: The remote data destination
    :param threaded:
    """
    sftp_conn = client.open_sftp()
    get_files = []
    if not type(sources) is list:
        sources = [sources]
    for source in sources:
        if stat.S_ISDIR(sftp_conn.lstat(source).st_mode):
            for source_fn in _walk_files(pmk_walk(sftp_conn, source)):
                target_fn = os.path.join(target,
                                         os.path.relpath(source_fn, source))
                get_files.append((source_fn, target_fn))
        if os.path.isfile(source):
            get_files.append((source, target))
    _pmk_mover(pmk_get_file, client=client, file_tuples=get_files,
               threaded=threaded, thread_cap=thread_cap)


def pmk_get_file(client, source_fn, target_fn):
    """

    :param client:
    :param source_fn:
    :param target_fn:
    :return:
    """
    log = getLogger(__name__)
    sftp_conn = _open_sftp(client)
    os.makedirs(os.path.dirname(target_fn), exist_ok=True)
    log.debug("Sending %s to %s", source_fn, target_fn)
    sftp_conn.get(source_fn, target_fn)
    sftp_conn.close()
