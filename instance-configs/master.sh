#!/bin/bash

# master cluster AMI configuration, executed on top of the base cluster instance

# ==========
# Configure `cluster` user's .Rprofile to provide a function that automatically
# loads the provided hostfile and creates a PSOCK cluster
echo 'defaultCluster <- function(hostfile = "/home/cluster/hostfile") {
  hosts <- read.delim(hostfile, "\n", header = FALSE,
                      stringsAsFactors = FALSE)[,1]
  master_ip <- gsub("-", ".",
                    gsub("ip-", "", system("hostname", intern = TRUE)))
  parallel::makePSOCKcluster(hosts, rscript = "/usr/bin/Rscript",
                             user = "cluster", port = 42808,
                             master = master_ip)
}
' >> /home/cluster/.Rprofile


# ==========
# SSH
# Note, as the /home/cluster folder is shared across master and workers, they
# will all share the same /home/cluster/.ssh folder
mkdir /home/cluster/.ssh
ssh-keygen -t rsa -N "" -f /home/cluster/.ssh/id_rsa
cat /home/cluster/.ssh/id_rsa.pub >> /home/cluster/.ssh/authorized_keys

# Allow for first-login without confirming host (TODO: RStudio confirms host
# key checking)
echo 'Host *
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null' >> /home/cluster/.ssh/config

# Confirm all files in cluster folder are appropriately owned and SSH files have
# minimized access
chown -R cluster:cluster -R /home/cluster
chmod 700 -R /home/cluster/.ssh
chmod 644 /home/cluster/.ssh/authorized_keys


# ==========
# Download/install RStudio
wget https://download2.rstudio.org/rstudio-server-0.99.486-amd64.deb
gdebi -n rstudio-server-0.99.486-amd64.deb


# ==========
# Install NFS, mount `cluster` user home folder for sharing
apt-get -y install nfs-kernel-server
echo "ALL: 10.10." >> /etc/hosts.allow
echo "/home/cluster *(rw,sync,no_root_squash)" >> /etc/exports
service nfs-kernel-server restart
