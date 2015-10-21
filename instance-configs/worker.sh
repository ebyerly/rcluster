#!/bin/bash

# base cluster AMI configuration
# Designed for Ubuntu 14.04, ami-655e1000

# ==========
# Remove outdated R installation

# Uninstall, remove libraries
apt-get -y remove r-base r-base-core
rm -rf /usr/local/lib/R
rm -rf /usr/lib/R

# Add source for latest version of R, add needed key
echo "deb http://watson.nci.nih.gov/cran_mirror/bin/linux/ubuntu trusty/" >> \
/etc/apt/sources.list
apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 51716619E084DAB9


# ==========
# Installations

# Software: SSH, Git, Vim, NFS, R, gdebi and apparmor for RStudio, ODBC for
# SQL communication
apt-get -y install openssh-server openssh-client git vim nfs-common r-base-dev \
                   gdebi-core libapparmor1 libiodbc2-dev

# Update installations, clean unnecessary files
apt-get -y update
apt-get -y upgrade
apt-get -y autoremove

# Install R packages
R -e 'install.packages(c("stringr", "plyr", "dplyr", "caret", "MASS", "snow", "boot", "RODBC"), repo = "http://watson.nci.nih.gov/cran_mirror/")'


# ==========
# `cluster` user

# Add the `cluster` user
adduser cluster --gecos "cluster,,," --disabled-password

# Set the password (here, "cluster-base-password")
echo "cluster:cluster-base-password" | chpasswd

# Set the cluster user's home folder to automatically set permissions for the
# `cluster` user whenever a file is made in its home folder
chmod -R g+swrx /home/cluster
