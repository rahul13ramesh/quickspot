#!/usr/bin/env python3
"""
Usage:
  qs create   [<config_file>]
  qs start    [<name_tag>]
  qs connect  [<name_tag>]
  qs copyto   [<name_tag>]  --src=<src_file> --dst=<dest_file>
  qs copyfrom [<name_tag>]  --src=<src_file> --dst=<dest_file>
  qs list
  qs price
  qs (-h | --help)

Arguments:
  list           List Instances
  start          Start an on-demand instance
  connect        Connect to an active instance
  attach         Attach a volume
  create         Create a new spot instance request
  copyto         Copy from local to EC2 instance
  copyfrom       Copy from EC2 instance to local machine

Options:
  -h, --help     Show this screen.
"""
import json
import boto3
import numpy as np
import os
import pkg_resources
from appdirs import user_config_dir
from docopt import docopt
from colorama import Fore, Style
from tabulate import tabulate
from .spinner import run_spinner


class AwsCli():
    """
    Manage a single EC2 spot instance that uses
    exactly one AMI and one external volume.

    Functionality includes:
        * Attaching and detaching volumes
        * Creating, deleting, connecting to a spot instance
        * List prices of GPU EC2 instances
        * Fetch volumes, images and instances
        * Get current status of EC2 instances

    Populate config.json to use default variables
    asd
    """
    def __init__(self, access_key, secret_key, tags, keyName):
        self.client = boto3.client(
            'ec2',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
        self.tags = tags
        self.keyname = keyName

    def update_config(self, filepath):
        with open(filepath, "r") as fi:
            self.config = json.load(fi)

        self.config["KeyName"] = self.keyname
        if "volume-id" in self.config:
            self.volId = self.config["volume-id"]
            del self.config["volume-id"]
        else:
            self.volId = None

        if "tags" in self.config:
            for tg in self.config["tags"]:
                self.tags.append(tg)

            del self.config["tags"]
        else:
            self.tags = []

    def getZone(self, info):
        if 'Placement' in info:
            return info['Placement']['AvailabilityZone']
        else:
            return "--"

    def getVolumeMap(self):
        volMap = {}
        response = self.client.describe_volumes()
        for vol in response['Volumes']:
            if len(vol['Attachments']) != 0:
                machine = vol['Attachments'][0]
                if 'InstanceId' in machine:
                    if "sda1" not in machine['Device']:
                        size = str(vol['Size']) + 'GB'
                        volMap[machine['InstanceId']] = size
        return volMap

    def createInstance(self):

        instType = self.config['InstanceType']
        price = str(3 * float(np.mean(self.listPrices(instType))))

        response = self.client.request_spot_instances(
            SpotPrice=price,
            InstanceCount=1,
            Type='one-time',
            LaunchSpecification=self.config
        )
        reqId = response['SpotInstanceRequests'][0]['SpotInstanceRequestId']
        instId = self.waitSpot(reqId)
        if instId is not None:
            instStatus = self.waitInstance(instId)
            if instStatus == 0:
                self.tagResource(instId)
                if self.volId is not None:
                    self.attachVolume(instId, self.volId)
                    self.waitAttach(instId, self.volId)

                print("\nSuccessfully created a %s instance"
                      "\n   Instance ID: %s"
                      "\n   Request ID : %s" % (
                       self.config['InstanceType'],
                       instId, reqId))

    def start(self, name, owner):
        response = self.client.describe_instances()
        status = 0
        for inst in response['Reservations']:
            info = inst['Instances'][0]
            if self.getTag(info, 'owner') == owner:
                machName = self.getTag(info, 'Name')
                if (name is None) or machName == name:
                    status = 1
                    inst_id = info['InstanceId']
                    response = self.client.start_instances(
                        InstanceIds=[inst_id],
                    )
                    response = response['StartingInstances'][0]
                    if response['PreviousState']['Code'] == 16:
                        print("\nInstance %s is already running" % (name))
                    elif response['CurrentState']['Code'] <= 16:
                        print("\nInstance %s is had been started" % (name))
                    else:
                        print("\nUnable to start %s" % (name))
                    break
        if status == 0:
            print("Could not find instance %s" % (name))

    def tagResource(self, resourceId):
        self.client.create_tags(
            Resources=[resourceId],
            Tags=self.tags)

    def getTag(self, info, key):
        if 'Tags' in info:
            for tg in info['Tags']:
                if tg['Key'] == key:
                    return tg['Value']
        return "--"

    def waitSpot(self, reqId):
        """
        Returns:
            status:
               0 - fullfilled
               1 - Disabled, failed, closed, cancelled
               2 - No spot requests
        """
        instanceId = None
        for i in range(20):
            run_spinner('Creating Spot Request')
            try:
                response = self.client.describe_spot_instance_requests(
                    SpotInstanceRequestIds=[reqId])
            except:
                status = 1
                continue
            reqs = response['SpotInstanceRequests']
            state = reqs[0]['State']
            if state == 'open':
                status = -1
            elif state == 'active':
                instanceId = reqs[0]['InstanceId']
                status = 0
                break
            else:
                status = 1
                break
        if status == -1:
            print("\r [" + Fore.YELLOW + "•" + Style.RESET_ALL +
                  "] Spot request was Cancelled -"
                  "There was no Spot Capacity Availible")
            response = self.client.cancel_spot_instance_requests(
                SpotInstanceRequestIds=[reqId])
        elif status == 0:
            print("\r [" + Fore.GREEN + "•" + Style.RESET_ALL +
                  "] Spot request Fulfilled")
        elif status == 1:
            print("\r [" + Fore.RED + "•" + Style.RESET_ALL +
                  "] Spot request Failed - Bad Parameters / System Error")
        return instanceId

    def waitInstance(self, instId):

        for i in range(40):
            run_spinner('Initializing Instance')
            try:
                response = self.client.describe_instance_status(
                    InstanceIds=[instId],
                    IncludeAllInstances=True)
            except:
                status = 1
                continue
            state = response['InstanceStatuses'][0]['InstanceState']['Name']
            if state == 'pending':
                status = -1
            elif state == 'running':
                status = 0
                break
            else:
                status = 1
                break

        if status == -1:
            print("\r [" + Fore.YELLOW + "•" + Style.RESET_ALL +
                  "] Instance Pending")
        elif status == 0:
            print("\r [" + Fore.GREEN + "•" + Style.RESET_ALL +
                  "] Instance is running")
        elif status == 1:
            print("\r [" + Fore.RED + "•" + Style.RESET_ALL +
                  "] Failed to create an instance")
        return status

    def waitAttach(self, instId, volId):

        for i in range(20):
            run_spinner('Attaching volume')
            try:
                response = self.client.describe_volumes(
                    VolumeIds=[volId])
            except:
                status = 1
                break
            info = response['Volumes'][0]
            state = info['State']
            attach_state = True if len(info['Attachments']) > 0 else False
            if attach_state:
                attach_info = info['Attachments'][0]['State']
            else:
                status = 1
                break

            if state == 'deleted' or state == 'error':
                status = 1
                break
            elif attach_state and attach_info == 'attached':
                status = 0
                break
            else:
                status = -1

        if status == -1:
            print("\r [" + Fore.YELLOW + "•" + Style.RESET_ALL +
                  "] Attaching volume")
        elif status == 0:
            print("\r [" + Fore.GREEN + "•" + Style.RESET_ALL +
                  "] Succesfully attached volume")
        elif status == 1:
            print("\r [" + Fore.RED + "•" + Style.RESET_ALL +
                  "] Failed to attach volume")
        return status

    def listInstances(self):
        volMap = self.getVolumeMap()
        response = self.client.describe_instances()
        instanceTable = []
        header = ['User', 'Inst. Name', 'Type', 'State',
                  'Ext. Vol.', 'Zone']
        sortkey = []
        for inst in response['Reservations']:
            info = inst['Instances'][0]
            row = []
            row.append(self.getTag(info, 'owner'))
            sortkey.append(self.getTag(info, 'owner'))
            row.append(self.getTag(info, 'Name'))
            row.append(info['InstanceType'])
            row.append(info['State']['Name'])

            if info['InstanceId'] in volMap:
                row.append(volMap[info['InstanceId']])
            else:
                row.append("--")

            row.append(self.getZone(info))
            instanceTable.append(row)
        sortInd = list(np.argsort(sortkey))
        instanceTable = [instanceTable[i] for i in sortInd]

        print(tabulate(instanceTable, headers=header))

    def connect(self, name, owner, keypath):
        response = self.client.describe_instances()
        status = 0
        for inst in response['Reservations']:
            info = inst['Instances'][0]
            if self.getTag(info, 'owner') == owner:
                machName = self.getTag(info, 'Name')
                if (name is None) or machName == name:
                    if ('NetworkInterfaces' not in info or \
                              len(info['NetworkInterfaces']) == 0):
                        status = 1
                    else:
                        net = info['NetworkInterfaces'][0]
                        name = net['Association']['PublicDnsName']
                        ssh_cmd = ["ssh",
                                   "-i", keypath,
                                   "ubuntu@" + name]
                        print("Connecting....")
                        os.execvp('ssh', ssh_cmd)

        if status == 0:
            print('Instance \"' + str(name) + "\" does not exist")
        elif status == 1:
            print('Instance \"' + str(name) + "\" is not running")

    def copy(self, name, owner, keypath, tolocal, src, dst):
        response = self.client.describe_instances()
        status = 0
        for inst in response['Reservations']:
            info = inst['Instances'][0]
            if self.getTag(info, 'owner') == owner:
                machName = self.getTag(info, 'Name')
                if (name is None) or machName == name:
                    if 'NetworkInterfaces' not in info:
                        status = 1
                    else:
                        net = info['NetworkInterfaces'][0]
                        name = net['Association']['PublicDnsName']
                        scp_cmd = ["scp", "-r",
                                   "-i", keypath]
                        print('here')
                        print(scp_cmd)
                        if tolocal:
                            scp_cmd.append("ubuntu@" + name + ":" + src)
                            scp_cmd.append(dst)
                        else:
                            scp_cmd.append(src)
                            scp_cmd.append("ubuntu@" + name + ":" + dst)
                                   
                        print("Copying....")
                        os.execvp('scp', scp_cmd)

        if status == 0:
            print('Instance \"' + str(name) + "\" does not exist")
        elif status == 1:
            print('Instance \"' + str(name) + "\" is not running")

    def attachVolume(self, instId, volId):
        self.client.attach_volume(
            Device="/dev/sdh",
            InstanceId=instId,
            VolumeId=volId)

    def describeVolume(self, instId, volId):
        self.client.attach_volume(
            Device="/dev/sdh",
            InstanceId=instId,
            VolumeId=volId)

    def listPrices(self, instance=None):
        if instance is None:
            instanceSet = [
                'g3s.xlarge', "g3.4xlarge", "g3.8xlarge",
                'g4dn.xlarge', 'g4dn.metal', 'g4dn.2xlarge',
                'g4dn.4xlarge', 'g4dn.8xlarge', 'p2.xlarge',
                'p2.8xlarge', 'p3.2xlarge', 'p3.8xlarge']
        else:
            instanceSet = [instance]

        response = self.client.describe_spot_price_history(
            AvailabilityZone='us-east-1b',
            InstanceTypes=instanceSet,
            MaxResults=30,
            ProductDescriptions=[
                'Linux/UNIX',
            ])
        priceMap = {}
        for priceInfo in response['SpotPriceHistory']:
            name = priceInfo['InstanceType']
            if name not in priceMap:
                priceMap[name] = []
            priceMap[name].append(float(priceInfo['SpotPrice']))

        if instance is None:
            for inst in sorted(priceMap):
                print("%s \t %0.3f" % (inst, np.mean(priceMap[inst])))
        else:
            return priceMap[instance]


def find_file(fname):
    if ".json" not in fname:
        fname = fname + ".json"
    fname = os.path.join(user_config_dir('aws'), fname)
    return fname


def getOwnerTag_fromGlobConfig(config):
    for tg in config["tags"]:
        if tg['Key'] == 'owner':
            return tg['Value']
    else:
        raise ValueError("Config file has no tag owner")


def main():
    arguments = docopt(__doc__, version='Aws Cli for Spot Instances')

    glob_file = os.path.join(user_config_dir('aws'), "global_config.json")
    with open(glob_file, "r") as fi:
        glob_config = json.load(fi)

    if arguments['<config_file>'] is not None:
        fname = find_file(arguments['<config_file>'])
    else:
        fname = find_file(glob_config["defaultConfig"])

    aws_access_key_id = glob_config["aws_access_key_id"]
    aws_secret_access_key = glob_config["aws_secret_access_key"]
    tags = glob_config["tags"]
    aws = AwsCli(aws_access_key_id, aws_secret_access_key,
                 tags, glob_config["KeyName"])

    if arguments['create']:
        aws.update_config(fname)
        aws.createInstance()
    elif arguments['list']:
        aws.listInstances()
    elif arguments['price']:
        aws.listPrices()
    elif arguments['start']:
        owner = getOwnerTag_fromGlobConfig(glob_config)
        aws.start(arguments['<name_tag>'], owner)
    elif arguments['connect']:
        owner = getOwnerTag_fromGlobConfig(glob_config)
        aws.connect(arguments['<name_tag>'], owner,
                    glob_config["pem-file"])
    elif arguments['copyfrom']:
        owner = getOwnerTag_fromGlobConfig(glob_config)
        aws.copy(arguments['<name_tag>'], owner,
                 glob_config["pem-file"], tolocal=True,
                 src=arguments['--src'], dst=arguments['--dst'])
    elif arguments['copyto']:
        owner = getOwnerTag_fromGlobConfig(glob_config)
        aws.copy(arguments['<name_tag>'], owner,
                 glob_config["pem-file"], tolocal=False,
                 src=arguments['--src'], dst=arguments['--dst'])


if __name__ == '__main__':
    main()
