rcluster makes launching and accessing an R cluster on AWS simple and
accessible.

This repository will:

* Create a connection to your AWS account
* Create and save an AMI with the software and configuration needed
* Allow you to launch a manager and a stated number of worker nodes, automating
  the network connections between them and hosting a common NFS-based home
  folder under the default `cluster` user:
    * "/home/cluster" is shared between manager and all workers
    * "/home/cluster/hostfile" contains the IPs of accessible worker nodes and
      spare manager nodes, repeated based on the number of available worker cores
    * `cluster` user's ".Rprofile" defines the R function `defaultCluster()`
      that automatically reference the hostfile to create a PSOCK-based cluster

After that, login to RStudio Server as normal on the manager, run
`defaultCluster()`, and use the returned parallel cluster object with
`parLapply()` and its peers.


# Getting Started

First, you must create and save locally your AWS access key ID and secret access
key ([instructions](http://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSGettingStartedGuide/AWSCredentials.html)).

Next, run `rcluster-config` from your command line. Note that this function
will, by default, write your AWS access key and secret access key to a hidden
folder in your user directory with no additional security.

There are currently three functions to launch and manage an R cluster:

* `rcluster` - Launch an R cluster on AWS using the default configuration file.
    This function will open your default browser to the RStudio Server login
    page on the manager instance once it is live.
* `rcluster-open` - Access an active R cluster (opens a new tab in your web
    browser to the RStudio Server instance, if available).
* `rcluster-terminate` - Terminate all instances associated with your `rcluster`
    configuration.
