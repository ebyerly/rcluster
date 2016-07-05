import os
import json
from time import sleep
from inspect import signature
from pprint import PrettyPrinter
from threading import Thread, Lock
from logging import getLogger
from boto3 import session

import rcluster as rcl


class RCluster:
    """RCluster class object

    Designed to organize the information for a boto3 connection to EC2, paramiko
    connections using a consistent SSH key, creation of EC2 instances using a
    consistent key, the creation and tracking of manager and worker nodes
    comprising an R PSOCK cluster, and networking those manager and worker
    nodes to access within an RStudio Server session.
    
    .. automethod:: __repr__
    .. automethod:: __setattr__
    
    """

    def __init__(self, aws_access_key_id, aws_secret_access_key, region_name,
                 instance_conf, manager_runtime=None, worker_runtime=None,
                 key_path=None, ip_ref='public_ip_address', ver=rcl.__ver__,
                 purge=False):
        """Initialize the RCluster object.
        
        :param aws_access_key_id: AWS access key provided to
            boto3.session.Session()
        :param aws_secret_access_key: AWS secret access key provided to
            boto3.session.Session()
        :param region_name: The accessibility region provided to
            boto3.session.Session()
        :param instance_conf: Dictionary defining {'ami': '', 'type': ''} for
            instances (where 'ami' is the AMI ID for the instances and type is
            the instance type used); can also contain other parameters to
            boto3's EC2.ServiceResource.create_instances
        :param manager_runtime: String containing shell runtime command for the
            manager instance
        :param worker_runtime: String containing shell runtime command for the
            worker instance
        :param key_path: The path to the key used to create EC2 instances and to
            connect to them using paramiko clients
        :param ip_ref: Whether to provide the user with the public IP or private
            IP
        :param ver: Designated to stamp Security Groups, Placement Groups, keys,
            and all instances launched
        """
        self._kwargs = list(signature(RCluster).parameters.keys())
        self._kwargs.remove('purge')
        self._config = {}
        self._log = getLogger(__name__)
        self.ses = session.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name
        )
        self.ec2 = self.ses.resource('ec2')
        if purge:
            _ec2_purge(self.ec2, ver)

        if not key_path:
            self.key_name = ver
            key_path = rcl._set_data('pem')
            kp = self.ec2.create_key_pair(KeyName=ver)
            with open(key_path, 'w') as out:
                out.write(kp.key_material)
        else:
            self.key_name = os.path.splitext(os.path.basename(key_path))[0]

        if 'SecurityGroups' not in instance_conf:
            sg = self.ec2.create_security_group(
                GroupName=ver,
                Description='22 and 8787 open, permissive internal traffic.'
            )
            instance_conf['SecurityGroups'] = [ver]
            sleep(1)  # Security group may not "exist" in time for next call
            sg.authorize_ingress(IpProtocol='tcp', FromPort=22, ToPort=22,
                                 CidrIp='0.0.0.0/0')
            sg.authorize_ingress(IpProtocol='tcp', FromPort=8787, ToPort=8787,
                                 CidrIp='0.0.0.0/0')
            sg.authorize_ingress(SourceSecurityGroupName=ver)

        if 'Placement' not in instance_conf:
            pg = self.ec2.create_placement_group(GroupName=ver,
                                                 Strategy='cluster')
            instance_conf['Placement'] = {'GroupName': ver}

        for key in self._kwargs:
            self.__setattr__(key, locals()[key])

    def __repr__(self):
        """Indicates RCluster and pretty prints the _config dictionary"""
        return 'RCluster class object\n' + PrettyPrinter().pformat(
            self._config)

    def __setattr__(self, key, value):
        """
        Redefined to keep an updated version of the :class:`~rcluster.RCluster`
        configuration options saved. Allows for easy exporting, duplication,
        and modification of configurations.
        
        See :meth:`~.rcluster.RCluster.fromConfig` and
        :meth:`~.rcluster.RCluster.writeConfig`
        """
        if '_config' in self.__dict__ and key in self._kwargs:
            self._log.debug('Setting configuration attribute %s', key)
            self._config[key] = value
        super().__setattr__(key, value)

    def write_config(self, fn):
        """Write out RCluster configuration data as JSON.

        :param fn: The filename to be written, will overwrite previous file
        """
        with open(fn, 'w') as out:
            json.dump(self._config, out, indent=2, sort_keys=True)

    def from_config(fn, **kwargs):
        """
        Use RCluster JSON configuration to create RCluster object.
        Prompts the user to input mandatory configuration values that are
        missing (i.e., AWS access credentials).

        :param fn: The filename containing RCluster configuration data
        :param kwargs: Alternate or supplement RCluster configuration; will
            override the content of fn
        """
        with open(fn, 'r') as out:
            dic = json.load(out)
        dic.update(kwargs)
        for key in sorted(dic):
            if dic[key] is None:
                dic[key] = input(key + ': ')
        return RCluster(**dic)

    def create_instances(self, n_instances, **kwargs):
        """Create EC2 instances using RCluster's configuration.

        :param n_instances: The number of instances to be created
        :param kwargs: arbitrary arguments to boto3 Session Resource
            ec2.create_instances; will supersede RCluster.instance_conf content
        """
        self._log.debug('Creating %d instances.', n_instances)
        conf = self.instance_conf.copy()
        conf.update(kwargs)
        instances = self.ec2.create_instances(
            DryRun=False,
            MinCount=n_instances,
            MaxCount=n_instances,
            KeyName=self.key_name,
            **conf
        )
        instances[0].wait_until_running()
        sleep(5)
        for instance in instances:
            instance.create_tags(DryRun=False,
                                 Tags=[{'Key': 'rcluster', 'Value': self.ver}])
        ids = [instance.id for instance in instances]
        return list(self.ec2.instances.filter(InstanceIds=ids))

    def create_cluster(self, n_workers=0, setup_pause=40, **kwargs):
        """Initialize the cluster.
        Launch a manager instance and n_workers worker instances, automating the
        configuration of their shared networking.

        :param n_workers: Number of worker instances to launch (default 1)
        :param setup_pause: Pause time to allow manager and workers to boot
            before attempting configuration steps (default 60)
        """
        if 'rcluster' in self.__dict__:
            if self.rcluster:
                self._log.debug('Active cluster found, returned.')
                return self.rcluster
        self._log.debug('Creating cluster of %d workers.', n_workers)
        instances = self.create_instances(n_workers + 1, **kwargs)
        sleep(setup_pause)
        try:
            manager = instances[0]
            manager.create_tags(DryRun=False,
                                Tags=[{'Key': self.ver, 'Value': 'manager'}])
            workers = instances[1:]
            self.manager_private = getattr(manager, 'private_ip_address')
            self.hostfile = ''
            hostfile_lock = Lock()
            worker_threads = []
            for worker in workers:
                worker_thread = Thread(target=self._configure_instance,
                                       kwargs={
                                           "instance": worker,
                                           "runtime": self.worker_runtime,
                                           "hostfile_lock": hostfile_lock
                                       })
                worker_thread.start()
                worker_threads.append(worker_thread)
            for worker_thread in worker_threads:
                worker_thread.join()
            self._configure_instance(manager, self.manager_runtime,
                                     hostfile_lock)
        except Exception as err:
            [instance.terminate() for instance in instances]
            self._log.error('Error during instance configuration: %s', err)
            raise err
        self.manager_ssh = self.connect(manager)
        self.rcluster = instances
        return self.rcluster

    def _configure_instance(self, instance, runtime, hostfile_lock):
        self._log.debug('Configuring instance %s', instance.instance_id)
        client = self.connect(instance)
        cpus = rcl.cpu_count(client)
        with hostfile_lock:
            self.hostfile += (instance.private_ip_address + '\n') * cpus
        if runtime:
            rcl.pmk_cmd(client, runtime.format(**self.__dict__))

    def connect(self, instance):
        """
        Create SSH connection to boto3.EC2.Instance as paramiko.client.

        :param instance: A boto3.EC2.Instance object
        """
        host = getattr(instance, self.ip_ref)
        key_path = self.key_path
        return rcl.pmk_connect(host, key_path)

    def get_manager(self):
        """
        Identify the manager  (if a manager has been defined) and return it.
        
        :return: list of identified ver/manager or None
        """
        if 'rcluster' in self.__dict__:
            if self.rcluster:
                return self.rcluster[0]
        manager = list(self.ec2.instances.filter(
            DryRun=False,
            Filters=[
                {'Name': 'tag-key', 'Values': [self.ver]},
                {'Name': 'tag-value', 'Values': ['manager']},
                {'Name': 'instance-state-name',
                 'Values': ['running', 'pending']}
            ]))
        if manager:
            return manager
        else:
            self._log.info("No active rcluster found")
            return None

    def get_manager_ip(self):
        """
        Identify the manager's access IP address (if a manager has been defined).
        """
        manager = self.get_manager()
        if manager:
            return getattr(manager[0], self.ip_ref)

    def get_instances(self, ver=None):
        if not ver:
            ver = self.ver
        instances = self.ec2.instances.filter(
            DryRun=False,
            Filters=[
                {'Name': 'tag-key', 'Values': ['rcluster']},
                {'Name': 'tag-value', 'Values': [ver]},
                {'Name': 'instance-state-name',
                 'Values': ['running', 'pending']}
            ])
        return list(instances)

    def terminate_instances(self, ver=None):
        """
        Terminate all EC2.Instance objects created by the current configuration
        file.
        """
        instances = self.get_instances(ver)
        if instances:
            [instance.terminate() for instance in instances]
        else:
            self._log.debug("No instances terminated.")

    def create_ami(self, base=None, setup_fn=None, ver=None, update_image=True,
                   terminate=True, wait=True):
        """
        Create an AMI, returning the AMI ID.

        :param base: boto3.EC2.Instance object or nothing; optional to allow for
            snapshotting.
        :param setup_fn: The shell script used to configure the instance;
            optional to allow for snapshotting.
        :param ver: Name of AMI, defaults to self.ver.
        :param update_image: Flag; whether to change the RCluster's
            instance_conf AMI ID to that of the new image.
        :param terminate: Flag; whether to terminate the instance used to build
            the AMI (useful for debugging).
        """
        if not base:
            self._log.debug('Creating base instance for AMI generation.')
            base = self.create_instances(1, InstanceType='m4.large')[0]
            sleep(20)
        if setup_fn:
            client = self.connect(base)
            sftp_conn = client.open_sftp()
            sftp_conn.put(setup_fn, 'setup.sh')
            self._log.debug('Setup script %s, running configuration.', setup_fn)
            rcl.pmk_cmd(client, 'sudo bash setup.sh')
        if not ver:
            ver = self.ver
        self._log.debug('Creating AMI %s', self.ver)
        image = base.create_image(
            DryRun=False,
            Name=ver,
            Description="RCluster AMI",
            NoReboot=False
        )
        base.wait_until_running()
        if wait:
            while 'available' not in self.ec2.Image(image.id).state:
                self._log.debug('Waiting for AMI %s to be available', image.id)
                sleep(20)
        if terminate:
            base.terminate()
        if update_image:
            self.instance_conf['ImageId'] = image.id
        return image.id

    def put_data(self, sources, target=None, client=None, threaded=True):
        """

        :param sources:
        :param target:
        :param client:
        :param threaded:
        :return:
        """
        if not target:
            target = "/shared"
        if not client:
            client = self.manager_ssh
        rcl.pmk_put(client, sources, target, threaded=threaded)

    def get_data(self, target, sources=None, client=None, threaded=True):
        """

        :param target:
        :param sources:
        :param client:
        :param threaded:
        :return:
        """
        if not sources:
            sources = "/shared"
        if not client:
            client = self.manager_ssh
        rcl.pmk_get(client, sources, target, threaded=threaded)

    def issue_cmd(self, call, client=None, **kwargs):
        """

        :param call:
        :param client:
        :return:
        """
        if not client:
            client = self.manager_ssh
        return rcl.pmk_cmd(client, call, **kwargs)


def _ec2_purge(ec2_res, ver):
    """
    Utility to clear an AWS account of previous RCluster settings (useful for
    development). Removes resources associated with a provided version:
    
    * Terminates instances with the tag key 'rcluster' and value `ver`
    * Deregisters AMI named `ver`
    * Deletes key-pair named `ver`
    * Deletes placement group named `ver`
    * Deletes security group named `ver`

    :param ec2_res: A boto3.EC2.ServiceResource
    :param ver: The "version" to delete
    """
    log = getLogger(__name__)
    log.info('Purging %s configurations', ver)
    instances = ec2_res.instances.filter(
        DryRun=False,
        Filters=[
            {'Name': 'tag-key', 'Values': ['rcluster']},
            {'Name': 'tag-value', 'Values': [ver]},
            {'Name': 'instance-state-name',
             'Values': ['running', 'pending']}
        ])
    [instance.terminate() for instance in instances]
    images = ec2_res.images.filter(
        DryRun=False,
        Filters=[{'Name': 'name', 'Values': [ver]}]
    )
    [image.deregister() for image in images]
    key_pairs = ec2_res.key_pairs.filter(
        DryRun=False,
        Filters=[{'Name': 'key-name', 'Values': [ver]}]
    )
    [key_pair.delete() for key_pair in key_pairs]
    placement_groups = ec2_res.placement_groups.filter(
        DryRun=False,
        Filters=[{'Name': 'group-name', 'Values': [ver]}]
    )
    [placement_group.delete() for placement_group in placement_groups]
    security_groups = ec2_res.security_groups.filter(
        DryRun=False,
        Filters=[{'Name': 'group-name', 'Values': [ver]}]
    )
    [security_group.delete() for security_group in security_groups]
