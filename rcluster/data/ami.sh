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
# Add the `cluster` user

adduser cluster --gecos "cluster,,," --disabled-password


# ==========
# Configure `cluster` user's .Rprofile to provide a function that automatically
# loads the provided hostfile and creates a PSOCK cluster
echo 'defaultCluster <- function(hostfile = "/home/cluster/hostfile") {
  if (file.exists(hostfile)) {
    hosts <- read.delim(hostfile, "\n", header = FALSE,
                        stringsAsFactors = FALSE)[,1]
    master_ip <- gsub("-", ".", gsub("ip-", "",
                                     system("hostname", intern = TRUE)))
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

# Note, as the /home/cluster folder is shared across manager and workers, they
# will all share the same /home/cluster/.ssh folder
mkdir /home/cluster/.ssh
ssh-keygen -t rsa -N "" -f /home/cluster/.ssh/id_rsa

# Allow localhost logins
cat /home/cluster/.ssh/id_rsa.pub > /home/cluster/.ssh/authorized_keys

# Allow for first-login without confirming host (TODO: RStudio confirms host
# key checking?)
echo 'Host *
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null' >> /home/cluster/.ssh/config

# Confirm appropriate file ownership and permissions
chown cluster:cluster -R /home/cluster
chmod 0755 -R /home/cluster
chmod 0600 /home/cluster/.ssh/authorized_keys

# ==========
# NFS configuration

# Install NFS
apt-get -y install nfs-kernel-server

# Create an "open" folder for sharing data, writing data by SFTP
mkdir /shared
chmod 777 /shared

# Share folders across local connections
echo "ALL: 172. 192." >> /etc/hosts.allow
echo "/shared *(rw,sync,no_root_squash)
/home/cluster *(rw,sync,no_root_squash)" >> /etc/exports
