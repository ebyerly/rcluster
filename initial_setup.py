from rcluster import *


# Create the 'private' folder, not tracked by the git repository, to store files
# containing private keys and access secrets
try:
    os.makedirs('private')
except FileExistsError:
    pass


# Use initial_config.json RCluster JSON file to create RCluster class object; if
# initial_config.json has not been edited by the user, they will be prompted to
# provide access keys
# Includes automatic generation of an RCluster key-pair for SSH communication
setup_cl = RCluster.fromConfig("setup/initial_config.json")


# Create a security group that allows traffic on ports 22 (SSH) and 8787
# (RStudio Server) from any IP and all internal network traffic
sg = setup_cl.ec2.create_security_group(
    GroupName=setup_cl.ver,
    Description='22 and 8787 open to all IPs, permissive local traffic.'
)
sg.authorize_ingress(
    IpProtocol='tcp',
    FromPort=22,
    ToPort=22,
    CidrIp='0.0.0.0/0'
)
sg.authorize_ingress(
    IpProtocol='tcp',
    FromPort=8787,
    ToPort=8787,
    CidrIp='0.0.0.0/0'
)
sg.authorize_ingress(SourceSecurityGroupName = sg.group_name)
setup_cl.instance_conf['SecurityGroups'] = [sg.group_name]


# Create a placement group for faster inter-node communication
pg = setup_cl.ec2.create_placement_group(
    GroupName=setup_cl.ver,
    Strategy='cluster'
)
setup_cl.instance_conf['Placement'] = {'GroupName' : pg.group_name}


# Using an Ubuntu 14.04 EBS-backed AMI and specifying our type as m4.large,
# launch a blank image and run through the worker node configurations provided
# by "instance-configs/worker.sh".
# Note we assign the new AMI ID to setup_cl.instance_conf['ImageID']
base = setup_cl.createInstances(1)[0]
sleep(20)
client = setup_cl.pmkConnect(base)
conn_sftp = client.open_sftp()
conn_sftp.put('setup/ami.sh', 'setup.sh')
print('Setup script, setup/ami.sh, provided, running configuration.')
pmkCmd(client, 'sudo sh setup.sh')
print('Creating AMI', setup_cl.ver)
image = base.create_image(
    DryRun = False,
    Name = setup_cl.ver,
    Description = "RCluster AMI",
    NoReboot = False
)
base.wait_until_running()
sleep(20)
base.terminate()
setup_cl.instance_conf['ImageId'] = image.id


# We save out our configuration, which now includes AWS access keys and the
# cluster AMI, as basic_private.json. Note, the RCluster repository ignores
# files that contain *private*
setup_cl.writeConfig('private/' + setup_cl.ver + '.json')
