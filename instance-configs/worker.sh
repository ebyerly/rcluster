#!/bin/bash

# base cluster AMI configuration
# Designed for Ubuntu 14.04, ami-655e1000

# ==========
# Add source for latest version of R, add needed key
echo "deb http://watson.nci.nih.gov/cran_mirror/bin/linux/ubuntu trusty/" >> \
/etc/apt/sources.list
apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 51716619E084DAB9

# Update installations, clean unnecessary files
apt-get -y update
apt-get -y upgrade
apt-get -y autoremove

# Software
apt-get -y install openssh-server openssh-client
apt-get -y install nfs-common r-base-dev
apt-get -y install gdebi-core libapparmor1

# Install R packages
R -e 'install.packages(c("dplyr"), repo = "http://watson.nci.nih.gov/cran_mirror/")'


# ==========
# `cluster` user

# Add the `cluster` user
adduser cluster --gecos "cluster,,," --disabled-password

# Set the password (here, "cluster-base-password")
echo "cluster:cluster-base-password" | chpasswd

# Set the cluster user's home folder to automatically set permissions for the
# `cluster` user whenever a file is made in its home folder
chmod -R g+swrx /home/cluster
