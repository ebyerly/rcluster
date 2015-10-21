from rcluster import *

# Use basic_config RCluster JSON file to create RCluster class object; if
# basic_config.json has not been edited by the user, they will be prompted to
# provide access keys
basic_cluster = RCluster.fromConfig("cluster-configs/basic_config.json")

print("\nConfiguration of AMIs is beginning. If the attempt to make an SSH",
      "connection continues to fail, confirm that your EC2 default security",
      "group allows SSH traffic.\n")

# Using an Ubuntu 14.04 EBS-backed AMI and specifying our type as m4.large,
# launch a blank image and run through the worker node configurations provided
# by "instance-configs/worker.sh".
# Note we assign the new AMI ID to basic_cluster.worker_conf['ami']
base, basic_cluster.worker_conf['ami'] =\
    basic_cluster.createAmi("instance-configs/worker.sh",
                            "worker",
                            "worker AMI for use with RStudio",
                            base_ami = 'ami-655e1000',
                            instance_type = 'm4.large'
    )  

# AMI creation, by default, restarts the instance, so we wait for base to reboot
# and then pause for it to finish booting.
base.wait_until_running()
sleep(60)

# Providing base, an active instance, as our argument to .createAmi (instead of
# an AMI and an instance type), we now apply the additional configurations in
# "instance-configs/master.sh" and save this second AMI as the master AMI.
# Note we assign the new AMI ID to basic_cluster.master_conf['ami']
base, basic_cluster.master_conf['ami'] =\
    basic_cluster.createAmi("instance-configs/master.sh",
                            "master",
                            "master AMI for use with RStudio",
                            base = base
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
