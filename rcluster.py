import os
import json
from time import sleep, gmtime, strftime
from copy import deepcopy
from inspect import getargspec
from pprint import PrettyPrinter

from boto3 import session
import paramiko


class RCluster:
    '''RCluster class object
    
    Designed to organize the information for a boto3 connection to EC2, paramiko
    connections using a consistent SSH key, creation of EC2 instances using a
    consistent key, the creation and tracking of master and worker nodes
    comprising an R PSOCK cluster, and networking those master and worker
    nodes to access within an RStudio Server session.
    '''
    def __init__(self, aws_access_key_id, aws_secret_access_key, region_name,
                 key_path, instance_conf, master_conf, worker_conf,
                 sudo_user = 'ubuntu', ip_ref = 'public', instance_config = {}):
        '''Initialize the RCluster object.
        
        Keyword arguments:
        aws_access_key_id -- AWS access key provided to boto3.session.Session()
        aws_secret_access_key -- AWS secret access key provided to
            boto3.session.Session()
        region_name -- The accessibility region provided to
            boto3.session.Session()
        key_path -- The path to the key used to create EC2 instances and to
            connect to them using paramiko clients
        instance_conf -- Dictionary defining {'ami':, 'type':} for instances
            (where 'ami' is the AMI ID for the instances and type is the
            instance type used)
        master_conf -- Dictionary defining {'runtime':} for
            the master instance (where 'runtime' is a shell command issued after
            the master instance has finished booting)
        worker_conf -- Dictionary defining {'runtime':} for
            the worker instance (where 'runtime' is a shell command issued after
            the worker instance has finished booting)
        sudo_user -- The sudo user for all instances (default 'ubuntu')
        ip_ref -- 'public'|'private', the IP used to access instances from your
            local session (default 'public')
        instance_config -- Additional instance configuration options to be sent
            to boto3.session.Session().resource('ec2').create_instances() and
            unpacked (default {})
        '''
        self._kwargs = getargspec(RCluster)[0][1:]
        self._config = {}
        for key in self._kwargs:
            self.__setattr__(key, locals()[key])
        
        self.ses = session.Session(
            aws_access_key_id = aws_access_key_id,
            aws_secret_access_key = aws_secret_access_key, 
            region_name = region_name
        )
        self.ec2 = self.ses.resource('ec2')
        self.k = paramiko.RSAKey.from_private_key_file(key_path)
        self.key_name = os.path.splitext(os.path.basename(key_path))[0]
    
    def __repr__(self):
        '''Indicates object is class RCluster
        Prints the _config dictionary prettily.
        '''
        return 'RCluster class object\n' + PrettyPrinter().pformat(self._config)
    
    def __setattr__(self, key, value):
        '''__setattr__ special method redefined to keep an updated version of
        the RCluster configuration options saved. Allows for easy exporting and
        duplication of an RCluster configuration (see RCluster.fromConfig() and
        RCluster.writeConfig()).
        '''
        if '_config' in self.__dict__ and key in self._kwargs:
            print('Setting configuration attribute', key)
            self._config[key] = value
        super().__setattr__(key, value)
    
    def createCluster(self, n_workers = 1, setup_pause = 60):
        '''Initialize the cluster.
        Launch a master instance and n_workers worker instances, automating the
        configuration of their shared networking.
        
        Keyword arguments:
        n_workers -- Number of worker instances to launch (default 1)
        setup_pause -- Pause time to allow master and workers to boot before
            attempting configuration steps (default 60)
        '''
        print('Creating cluster of', n_workers, 'workers')
        instances = self.createInstances(self.instance_conf['ami'], n_workers + 1,
                                         self.instance_conf['type'])
        master = instances[0]
        workers = instances[1:]
        sleep(setup_pause)
        self.master_private = getattr(master, 'private_ip_address')
        self.access_ip = getattr(master,
                                 '{ip_ref}_ip_address'.format(**self.__dict__))
        try:
            self.hostfile = ''
            for worker in workers:
                print('Configuring Worker', worker.instance_id)
                client = self.pmkConnect(worker)
                cpus = cpuCount(client)
                self.hostfile += (worker.private_ip_address + '\n') * cpus
                if self.worker_conf['runtime']:
                    pmkCmd(client,
                           self.worker_conf['runtime'].format(**self.__dict__))
            print('Configuring Master', master.instance_id)
            client = self.pmkConnect(master)
            cpus = cpuCount(client) - 1
            self.hostfile += (master.private_ip_address + '\n') * cpus
            if self.master_conf['runtime']:
                pmkCmd(client,
                       self.master_conf['runtime'].format(**self.__dict__))
        except Exception as err:
            print('Error during instance configuration:', err)
            pass
        finally:
            self.master = master
            self.workers = workers
    
    def pmkConnect(self, instance, client = None):
        '''Create connection in SSHClient object, retrying on failure.
        
        Keyword arguments:
        instance -- The boto3 EC2 instance to which an SSH connection is made
        client -- paramiko client (default None)
        '''
        if not client:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.client.AutoAddPolicy())
        host = getattr(instance, '{0}_ip_address'.format(self.ip_ref))
        try:
            print(strftime('%Y-%m-%d %H:%M:%S - Connecting to host',
                           gmtime()), host)
            client.connect(hostname = host, username = self.sudo_user,
                           pkey = self.k)
            return client
        except (TimeoutError, ConnectionRefusedError) as err:
            print('OS error: {0}'.format(err))
            print('Connection failed, trying again. (Interrupt to end attempt)')
            sleep(20)
            return self.pmkConnect(instance, client)
        except Exception as err:
            print('Unexpected error:', err)
            raise err
    
    def createInstances(self, ami, n_instances, instance_type):
        '''Create EC2 instances.
        
        Keyword arguments:
        ami -- The AMI to be used in instance creation
        n_instances -- The number of instances to be created
        instance_type -- The type (e.g., 'm4.large') to be created
        '''
        print('Creating', n_instances, ami, 'as', instance_type)
        instances = self.ec2.create_instances(
            DryRun = False,
            ImageId = ami,
            MinCount = n_instances,
            MaxCount = n_instances,
            InstanceType = instance_type,
            KeyName = self.key_name,
            **self.instance_config
        )
        instances[0].wait_until_running()
        ids = [instance.instance_id for instance in instances]
        return list(self.ec2.instances.filter(InstanceIds = ids))
    
    def createAmi(self, sh_script, name, description = '', base_ami = None,
                  instance_type = None,  base = None, setup_pause = 60):
        '''Create an AMI using a locally stored shell script.
        
        Keyword arguments:
        sh_script -- The path to a shell script
        name -- AWS-registered name for the new AMI
        description -- AWS-registered description for the new AMI (default '')
        base_ami -- The AMI to be launched, off which the new AMI will be based
            (default None)
        instance_type -- The instance type to be used to launch the base_ami
            (default None)
        base -- Alternative to providing base_ami and instance_type is to
            provide a boto3 EC2 instance object (default None)
        setup_pause -- Pause time to allow instance to boot before attempting
        configuration steps (default 60)
        '''
        if not base:
            try:
                base = self.createInstances(base_ami, 1, instance_type)[0]
                sleep(setup_pause)
            except Exception as err:
                print('You must supply either an active instance or an AMI' +\
                      'and an instance type to be created.')
                raise err
        client = self.pmkConnect(base)
        conn_sftp = client.open_sftp()
        conn_sftp.put(sh_script, 'setup.sh')
        print('Setup script', sh_script, 'provided, running configuration.')
        pmkCmd(client, 'sudo sh setup.sh')
        print('Creating AMI', name, ':', description)
        image = base.create_image(
            DryRun = False,
            Name = name,
            Description = description,
            NoReboot = False
        )
        return base, image.id
    
    def writeConfig(self, fn):
        '''Write out RCluster configuration data as JSON.'''
        with open(fn, 'w') as out:
            json.dump(self._config, out, indent = 2, sort_keys = True)
    
    def fromConfig(fn):
        '''Use RCluster JSON configuration to create RCluster object.'''
        with open(fn, 'r') as out:
            dic = json.load(out)
        for key in sorted(dic):
            if dic[key] is None:
                dic[key] = input(key + ': ')
        return RCluster(**dic)

def cpuCount(client):
    cpus = pmkCmd(client,
                  r'cat /proc/cpuinfo | grep processor | wc -l')
    cpus = int(cpus[0][:-1]) # original format: ['2\n']
    return cpus

def pmkCmd(client, call):
    '''Issue command over SSH, treat execution failure as program failure.
    
    Keyword arguments:
    client -- paramiko SSHClient class object
    call -- String of shell command to be executed.
    '''
    stdin, stdout, stderr = client.exec_command(call)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status:
        print(stderr.readlines())
        raise Exception
    return stdout.readlines()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', type = str, nargs = 1,
                       default = 'cluster-configs/basic_private.json',
                       help = 'the JSON referenced as the configuration' +\
                              'dictionary container.')
    parser.add_argument('-w', '--workers', type = int, nargs = 1,
                       default = [1],
                       help = 'the number of workers to launch')
    args = parser.parse_args()
    try:
        cluster = RCluster.fromConfig(args.config)
        cluster.createCluster(args.workers[0])
        print(cluster.access_ip, 'served by:\n', cluster.hostfile)
    except FileNotFoundError:
        print('Run "create_amis.py", first, to generate your own private config',
              'file with the minimum necessary data to start an RStudio',
              'cluster.')
    except Exception as err:
        raise err

