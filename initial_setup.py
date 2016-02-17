from rcluster import *


# Use basic_config RCluster JSON file to create RCluster class object; if
# basic_config.json has not been edited by the user, they will be prompted to
# provide access keys
basic_cluster = RCluster.fromConfig("cluster-configs/basic_config.json")


# Create a security group that allows SSH and :8787 traffic from all sources
# and all internal network traffic
sg = basic_cluster.ec2.create_security_group(
    GroupName='cluster',
    Description='Allows SSH and :8787 traffic from all sources'
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
sg.authorize_ingress(
    SourceSecurityGroupName = sg.group_name
)
basic_cluster.instance_config['SecurityGroups'] = [sg.group_name]


# Create a placement group for faster inter-node communication
pg = basic_cluster.ec2.create_placement_group(
    GroupName='cluster',
    Strategy='cluster'
)
basic_cluster.instance_config['Placement'] = {'GroupName' : pg.group_name}


# Using an Ubuntu 14.04 EBS-backed AMI and specifying our type as m4.large,
# launch a blank image and run through the worker node configurations provided
# by "instance-configs/worker.sh".
# Note we assign the new AMI ID to basic_cluster.worker_conf['ami']
base, basic_cluster.instance_conf['ami'] =\
    basic_cluster.createAmi("instance-configs/ami.sh",
                            "cluster",
                            "AMI for use with RStudio",
                            base_ami = 'ami-655e1000',
                            instance_type = 'm4.large'
    )

# We wait for base to finish rebooting, pause to ensure AWS is finished copying
# data for the AMI, and then terminate the instance.
base.wait_until_running()
sleep(60)
base.terminate()


# We save out our configuration, which now includes AWS access keys and the
# master and worker AMIs, as basic_private.json. Note, the RCluster repository
# ignores files that contain *private*
basic_cluster.writeConfig("cluster-configs/basic_private.json")
