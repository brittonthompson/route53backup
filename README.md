# route53backup
## Lambda function to backup Route 53 zones and health checks to S3

The function is designed to trigger on CloudWatch Logs from CloudTrail using the following filter pattern: 

```
{ $.eventSource = "route53.*" } 
```

When a zone is changed the event fires and that zone is backed up as a json file to the given S3 bucket. Configure the bucket with versioning to keep a version history of each zone and record all changes. Healthchecks related to the zone are dumped to a json file named for the zone + _healthchecks.

### Environment Variables

- ```BUCKET``` : Where the zones are backed up to
- (optional) ```ZONE_ID``` : Specificy a single zone id to backup only that zone
- (optional) ```FULL_BACKUP``` : Set any value and all zones will be backed up
