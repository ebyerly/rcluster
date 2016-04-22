#!/bin/bash

# base cluster AMI configuration
# Designed for Ubuntu 14.04, ami-655e1000

# ==========
# Add source for latest version of R and required key
echo "deb http://watson.nci.nih.gov/cran_mirror/bin/linux/ubuntu trusty/" >> \
/etc/apt/sources.list
apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 51716619E084DAB9

# Update installations, clean unnecessary files
apt-get -y update
apt-get -y upgrade
apt-get -y autoremove

# Software
apt-get -y install openssh-server
apt-get -y install nfs-kernel-server
apt-get -y install r-base-dev
apt-get -y install gdebi-core
apt-get -y install libapparmor1

# Install R packages
R -e 'install.packages(c("dplyr"), repo = "http://watson.nci.nih.gov/cran_mirror/")'

# Download/install RStudio
wget https://download2.rstudio.org/rstudio-server-0.99.486-amd64.deb
gdebi -n rstudio-server-0.99.486-amd64.deb
rm rstudio-server-0.99.486-amd64.deb


# ==========
# `cluster` user

# Add the `cluster` user
adduser cluster --gecos "cluster,,," --disabled-password

# Set the password (here, "cluster-base-password")
echo "cluster:cluster-base-password" | chpasswd

# Set the cluster user's home folder to automatically set permissions for the
# `cluster` user whenever a file is made in its home folder
chmod -R g+swrx /home/cluster

# Mount `cluster` user home folder for local sharing
echo "ALL: 172." >> /etc/hosts.allow
echo "/home/cluster *(rw,sync,no_root_squash)" >> /etc/exports
service nfs-kernel-server restart


# ==========
# Configure `cluster` user's .Rprofile to provide a function that automatically
# loads the provided hostfile and creates a PSOCK cluster
echo 'defaultCluster <- function(hostfile = "/home/cluster/hostfile") {
  hosts <- read.delim(hostfile, "\n", header = FALSE,
                      stringsAsFactors = FALSE)[,1]
  manager_ip <- gsub("-", ".",
                    gsub("ip-", "", system("hostname", intern = TRUE)))
  parallel::makePSOCKcluster(hosts, rscript = "/usr/bin/Rscript",
                             user = "cluster", port = 42808,
                             manager = manager_ip)
}
' >> /home/cluster/.Rprofile


# ==========
# SSH
# Note, as the /home/cluster folder is shared across manager and workers, they
# will all share the same /home/cluster/.ssh folder
mkdir /home/cluster/.ssh
ssh-keygen -t rsa -N "" -f /home/cluster/.ssh/id_rsa
cat /home/cluster/.ssh/id_rsa.pub >> /home/cluster/.ssh/authorized_keys

# Allow for first-login without confirming host
echo 'Host *
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null' >> /home/cluster/.ssh/config

# Confirm all files in cluster folder are appropriately owned and SSH files have
# minimized access
chown -R cluster:cluster -R /home/cluster
chmod 700 -R /home/cluster/.ssh
chmod 644 /home/cluster/.ssh/authorized_keys
