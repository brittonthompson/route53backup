import boto3
import os
from os import environ
import json
import gzip
import base64

'''
The lambda function should trigger on CloudWatch logs from CloudTrail

Create a trail for write only events and point to that log group using this filter: { $.eventSource = "route53.*" }

Define the BUCKET environment variable with the name of the S3 bucket to write the zone json files to
'''

# function for common output
def print_info(log, zone, records):
    print('[{timestamp}] {region}\t{ip}\t{service}:{action}\trecordCount:{recordCount}\tzoneName:{zoneName}'.format(
        timestamp=log['eventTime'],
        region=log['awsRegion'],
        ip=log['sourceIPAddress'],
        service=log['eventSource'].split('.')[0],
        action=log['eventName'],
        recordCount=len(records),
        zoneName=zone['Name'][:-1]
    ))


# function to process the backup of the zones and health checks to s3
def route53_zone_dump(route53, s3, BUCKET, zones, log):
    '''
    :param route53: boto3.client('route53')
    :param s3: boto3.client('s3')
    :param BUCKET: s3 bucket name string (my-bucket-name)
    :param zones: list of 'HostedZones' returned by the route53 api calls
    :param log: deserialized message from a trigger event (json.loads(log_event["message"]))
    '''

    for z in zones:
        # define an empty arry to store our healthcheck ids
        healthcheck = []

        # pull all records from our zone with the discovered id
        paginator = route53.get_paginator('list_resource_record_sets')
        iterator = paginator.paginate(HostedZoneId=z['Id'])
        records = []

        # page through all records and append to the records list
        for page in iterator:
            records += page['ResourceRecordSets']

        # output some related info to console for logging
        print_info(log, z, records)

        # write a json zone file to s3 with all records and settings
        s3.Object(BUCKET, z['Name'] + 'json').put(Body=json.dumps(records))

        # check all records to see if there's a healthcheck association and record the ids
        for h in records:
            if 'HealthCheckId' in h.keys():
                healthcheck.append(route53.get_health_check(HealthCheckId=h['HealthCheckId']))

        # if a healthcheck was found create a json file containing all settings named for the zone _healthchecks
        if healthcheck:
            s3.Object(BUCKET, z['Name'][:-1] + '_healthchecks.json').put(Body=json.dumps(healthcheck))


def lambda_handler(event, context):

    # instantiate variables
    ZONE_ID = ''
    FULL_BACKUP = ''
    BUCKET = os.environ['BUCKET']

    # environment variables
    # set ZONE_ID to manually backup a specific zone on-demand
    if "ZONE_ID" in os.environ:
        ZONE_ID = os.environ['ZONE_ID']

    # set FULL_BACKUP to manually backup a all zones
    if "FULL_BACKUP" in os.environ:
        FULL_BACKUP = True

    route53 = boto3.client('route53')
    s3 = boto3.resource('s3')

    # collect data from our event so we know what the name of the secret is
    cw_data = event['awslogs']['data']
    compressed_payload = base64.b64decode(cw_data)
    uncompressed_payload = gzip.decompress(compressed_payload)
    payload = json.loads(uncompressed_payload)

    # grab our list of log events collected
    log_events = payload["logEvents"]

    for log_event in log_events:

        # trim the event down to the message data
        log = json.loads(log_event["message"])

        # establish the list of zones
        zones = []

        # if a zone id is not given in env and we have a zone id in our event set the ZONE_ID
        if not ZONE_ID and log['requestParameters']['hostedZoneId']:
            ZONE_ID = log['requestParameters']['hostedZoneId']

        # if a ZONE_ID was set run our logic
        if ZONE_ID:
            # get the zone information so we can apply names to our output
            zones += [route53.get_hosted_zone(Id=ZONE_ID)['HostedZone']]

        # if FULL_BACKUP is set run the logic on all zones
        if FULL_BACKUP:

            # pull all zones
            paginator = route53.get_paginator('list_hosted_zones')
            iterator = paginator.paginate()

            # page through all zones and append to the zones list
            for page in iterator:
                zones += page['HostedZones']

        # process the backups of the zone(s)
        route53_zone_dump(route53, s3, BUCKET, zones, log)
