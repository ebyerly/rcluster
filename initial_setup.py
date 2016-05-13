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


# Using an Ubuntu 14.04 EBS-backed AMI and specifying our type as m4.large,
# launch a blank image and run through the worker node configurations provided
# by "instance-configs/worker.sh".
# Note we assign the new AMI ID to setup_cl.instance_conf['ImageID']
setup_cl.createAmi('setup/ami.sh')


# We save out our configuration, which now includes AWS access keys and the
# cluster AMI, as basic_private.json. Note, the RCluster repository ignores
# files that contain *private*
setup_cl.writeConfig('private/' + setup_cl.ver + '.json')
