import os
import json
from time import sleep, gmtime, strftime
from copy import deepcopy
from inspect import getargspec
from pprint import PrettyPrinter

from boto3 import session
import paramiko

ver = 'rcluster.0.1'

class RCluster:
    '''RCluster class object
    
    Designed to organize the information for a boto3 connection to EC2, paramiko
    connections using a consistent SSH key, creation of EC2 instances using a
    consistent key, the creation and tracking of manager and worker nodes
    comprising an R PSOCK cluster, and networking those manager and worker
    nodes to access within an RStudio Server session.
    '''
    def __init__(self, aws_access_key_id, aws_secret_access_key, region_name,
                 instance_conf, manager_runtime, worker_runtime, key_path = None,
                 ip_ref = 'public', ver = ver):
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
        manager_runtime -- Dictionary defining {'runtime':} for
            the manager instance (where 'runtime' is a shell command issued after
            the manager instance has finished booting)
        worker_runtime -- Dictionary defining {'runtime':} for
            the worker instance (where 'runtime' is a shell command issued after
            the worker instance has finished booting)
        ip_ref -- 'public'|'private', the IP used to access instances from your
            local session (default 'public')
        instance_conf -- Additional instance configuration options to be sent
            to boto3.session.Session().resource('ec2').create_instances() and
            unpacked (default {})
        '''
        self._kwargs = getargspec(RCluster)[0][1:]
        self._config = {}
        self.ses = session.Session(
            aws_access_key_id = aws_access_key_id,
            aws_secret_access_key = aws_secret_access_key, 
            region_name = region_name
        )
        self.ec2 = self.ses.resource('ec2')
        if not key_path:
            key_path = 'private/' + ver + '.pem'
            kp = self.ec2.create_key_pair(KeyName=ver)
            with open(key_path, 'w') as out:
              out.write(kp.key_material)
        for key in self._kwargs:
            self.__setattr__(key, locals()[key])

    
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
        Launch a manager instance and n_workers worker instances, automating the
        configuration of their shared networking.
        
        Keyword arguments:
        n_workers -- Number of worker instances to launch (default 1)
        setup_pause -- Pause time to allow manager and workers to boot before
            attempting configuration steps (default 60)
        '''
        print('Creating cluster of', n_workers, 'workers.')
        instances = self.createInstances(n_workers + 1)
        manager = instances[0]
        workers = instances[1:]
        sleep(setup_pause)
        self.manager_private = getattr(manager, 'private_ip_address')
        self.access_ip = getattr(manager,
                                 '{ip_ref}_ip_address'.format(**self.__dict__))
        try:
            self.hostfile = ''
            for worker in workers:
                print('Configuring Worker', worker.instance_id)
                client = self.pmkConnect(worker)
                cpus = cpuCount(client)
                self.hostfile += (worker.private_ip_address + '\n') * cpus
                if self.worker_runtime:
                    pmkCmd(client, self.worker_runtime.format(**self.__dict__))
            print('Configuring manager', manager.instance_id)
            client = self.pmkConnect(manager)
            cpus = cpuCount(client) - 1
            self.hostfile += (manager.private_ip_address + '\n') * cpus
            if self.manager_runtime:
                pmkCmd(client, self.manager_runtime.format(**self.__dict__))
        except Exception as err:
            print('Error during instance configuration:', err)
            pass
        finally:
            self.manager = manager
            self.workers = workers
    
    def pmkConnect(self, instance):
        '''Create connection in SSHClient object, retrying on failure.
        
        Keyword arguments:
        instance -- The boto3 EC2 instance to which an SSH connection is made
        client -- paramiko client (default None)
        '''
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.client.AutoAddPolicy())
        host = getattr(instance, '{0}_ip_address'.format(self.ip_ref))
        try:
            print(strftime('%Y-%m-%d %H:%M:%S - Connecting to host',
                           gmtime()), host)
            k = paramiko.RSAKey.from_private_key_file(self.key_path)
            client.connect(hostname = host, username = 'ubuntu', pkey = k)
            return client
        except (TimeoutError, ConnectionRefusedError, TypeError) as err:
            print('OS error:', err)
            print('Connection failed, trying again. (Interrupt to end attempt)')
            sleep(10)
            return self.pmkConnect(instance)
        except Exception as err:
            print('Connection failed, unexpected error:', err)
            raise err
    
    def createInstances(self, n_instances):
        '''Create EC2 instances.
        
        Keyword arguments:
        n_instances -- The number of instances to be created
        instance_type -- The type (e.g., 'm4.large') to be created
        '''
        print('Creating', n_instances, 'instances.')
        instances = self.ec2.create_instances(
            DryRun = False,
            MinCount = n_instances,
            MaxCount = n_instances,
            KeyName = self.ver,
            **self.instance_conf
        )
        instances[0].wait_until_running()
        sleep(5)
        ids = [instance.instance_id for instance in instances]
        return list(self.ec2.instances.filter(InstanceIds = ids))

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
                       default = 'private/' + ver + '.json',
                       help = 'the JSON referenced as the configuration' +\
                              'dictionary container.')
    parser.add_argument('-w', '--workers', type = int, nargs = 1,
                       default = [1],
                       help = 'the number of workers to launch')
    args = parser.parse_args()
    try:
        cluster = RCluster.fromConfig(args.config)
        cluster.createCluster(args.workers[0])
        print('Master IP Address:', cluster.access_ip,
              '\n\nserved by:\n', cluster.hostfile)
    except FileNotFoundError:
        print('Run "initial_setup.py", first, to generate your own config',
              'file with the minimum necessary data to start an RStudio',
              'cluster.')
    except Exception as err:
        raise err
