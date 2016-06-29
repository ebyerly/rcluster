#!/usr/bin/env bash

# base cluster AMI configuration
# Designed for Ubuntu 14.04, ami-0d729a60

# ==========
# Installations

# Add source for latest version of R, add needed key
apt-key adv --keyserver keyserver.ubuntu.com --recv-keys E084DAB9
add-apt-repository "deb https://cran.cnr.berkeley.edu/bin/linux/ubuntu trusty/"
add-apt-repository ppa:marutter/rdev

# Update installations, clean unnecessary files
apt-get -y check
apt-get -y clean
apt-get -y autoremove
apt-get -y update
apt-get -y upgrade

# Software: SSH, Git, Vim, NFS, R, gdebi and apparmor for RStudio
apt-get -qfy install r-base-dev openssh-server nfs-common gdebi-core \
    libapparmor1 git vim libgdal-dev libproj-dev

# Download/install RStudio
wget https://download2.rstudio.org/rstudio-server-0.99.896-amd64.deb
gdebi --non-interactive rstudio-server-0.99.896-amd64.deb


# ==========
# `cluster` user

# Add the `cluster` user
adduser cluster --gecos "cluster,,," --disabled-password

# Set the cluster user's home folder to automatically set permissions for the
# `cluster` user whenever a file is made in its home folder
chmod -R g+swrx /home/cluster

# Add `ubuntu` to cluster's user group, so SSH/SFTP connections can read and
# write into the home folder.
usermod -aG cluster ubuntu


# ==========
# Configure `cluster` user's .Rprofile to provide a function that automatically
# loads the provided hostfile and creates a PSOCK cluster
echo 'defaultCluster <- function(hostfile = "/home/cluster/hostfile") {
  if (file.exists(hostfile)) {
    hosts <- read.delim(hostfile, "\n", header = FALSE,
                        stringsAsFactors = FALSE)[,1]
    master_ip <- gsub("-", ".",
                      gsub("ip-", "", system("hostname", intern = TRUE)))
    parallel::makePSOCKcluster(hosts, rscript = "/usr/bin/Rscript",
                               user = "cluster", port = 42808,
                               master = master_ip)
  } else {
    parallel::makePSOCKcluster(parallel::detectCores())
  }
}
' >> /home/cluster/.Rprofile


# ==========
# SSH
# Note, as the /home/cluster folder is shared across master and workers, they
# will all share the same /home/cluster/.ssh folder
mkdir /home/cluster/.ssh
ssh-keygen -t rsa -N "" -f /home/cluster/.ssh/id_rsa
cat /home/cluster/.ssh/id_rsa.pub >> /home/cluster/.ssh/authorized_keys

# Allow for first-login without confirming host
# (TODO: RStudio confirms host key checking?)
echo 'Host *
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null' >> /home/cluster/.ssh/config

# Confirm SSH files have minimized access
chmod 700 -R /home/cluster/.ssh
chmod 644 /home/cluster/.ssh/authorized_keys


# ==========
# Install NFS, mount `cluster` user home folder for sharing
apt-get -y install nfs-kernel-server
echo "ALL: 10.10." >> /etc/hosts.allow
echo "/home/cluster *(rw,sync,no_root_squash)" >> /etc/exports
