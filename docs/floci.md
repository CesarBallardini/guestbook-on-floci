# Floci: looking at what is running

Three ways to see the resources the guestbook uses in the emulator: the web console, the
emulator's own URLs, and the AWS CLI. All of them need the stack up (README, steps 2 to 4).

## 1. The web console

Open <http://127.0.0.1:4566/_floci/ui>. The first time, Floci downloads the console's image and
starts it as one more container, `floci-aws-ui`; the page waits and then moves to
<http://127.0.0.1:4500/>.

| Page | Shows |
|---|---|
| <http://127.0.0.1:4500/console/aws> | The console's home |
| <http://127.0.0.1:4500/cloud-explorer/aws/compute> | The EC2 instance, `guestbook` |

The console's port is bound to `127.0.0.1` (`FLOCI_SERVICES_UI_BIND_ADDRESS` in
`compose.yaml`). The console has no login: whoever reaches the port sees
everything, which is why the bind address matters.

## 2. What `http://127.0.0.1:4566/` answers

Port 4566 is the AWS API, not a web site. It is the one address every AWS client talks to, for
every service. Floci tells the services apart by how each request is signed and shaped.

A browser sends a plain `GET /` with no signature. Floci takes that as the S3 call "list my
buckets", so the browser shows S3's answer, in XML:

```xml
<ListAllMyBucketsResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Owner><ID>f7b1…</ID><DisplayName>floci</DisplayName></Owner>
  <Buckets>
    <Bucket>
      <Name>guestbook-pictures</Name>
      <CreationDate>2026-11-19T16:14:52Z</CreationDate>
    </Bucket>
  </Buckets>
</ListAllMyBucketsResult>
```

| Part | Means |
|---|---|
| `Owner` | The emulated account that owns the buckets. Always `floci` |
| `Buckets` | Every S3 bucket in the emulator. Here, the one Terraform created for the pictures |
| `CreationDate` | When the bucket was created, in UTC |

So this page lists buckets and nothing else: no instance, no database, no load balancer. For
those, use the console or the AWS CLI.

Floci also answers a few addresses of its own, under `/_floci/`. They describe the emulator,
not the resources in it:

| URL | Answers |
|---|---|
| <http://127.0.0.1:4566/_floci/health> | Floci's version, and for each AWS service whether the emulator serves it (`running`). A service is listed whether or not anything was created in it |
| <http://127.0.0.1:4566/_floci/info> | The emulator's settings: version, edition, endpoint, which services are enabled |
| <http://127.0.0.1:4566/_floci/init> | Which start-up stages finished, and the scripts they ran (none here) |
| <http://127.0.0.1:4566/_floci/ui/status> | Whether the console is ready, and its URL |

## 3. The AWS CLI

Install it with `choco install awscli`. The keys can be any text; the endpoint is what sends
the calls to the emulator instead of AWS. In Git Bash:

```bash
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
alias awsl='aws --endpoint-url http://127.0.0.1:4566'
```

In PowerShell:

```powershell
$env:AWS_ACCESS_KEY_ID = "test"; $env:AWS_SECRET_ACCESS_KEY = "test"; $env:AWS_DEFAULT_REGION = "us-east-1"
function awsl { aws --endpoint-url http://127.0.0.1:4566 @args }
```

The examples below are for Git Bash. In PowerShell, the one with `$( )` works as written too.

**The instance:** its id, its state and its address on the Docker network.

```bash
awsl ec2 describe-instances --query 'Reservations[].Instances[].[InstanceId,State.Name,PrivateIpAddress]' --output table
```

```
+----------------------+----------+--------------+
|  i-77abfa3765f518bba |  running |  172.22.0.5  |
+----------------------+----------+--------------+
```

Instances that were replaced stay in the list for a while, as `terminated`.

**The pictures:** one object per picture a visitor attached. Empty until somebody does.

```bash
awsl s3 ls s3://guestbook-pictures
```

**The database:** `available` means it accepts connections. The address is the one the
instance uses.

```bash
awsl rds describe-db-instances --query 'DBInstances[].[DBInstanceIdentifier,DBInstanceStatus,Endpoint.Address,Endpoint.Port]' --output table
```

```
+-----------+-------------+----------------+-------+
|  guestbook|  available  |  aws-emulator  |  7001 |
+-----------+-------------+----------------+-------+
```

**The load balancer:**

```bash
awsl elbv2 describe-load-balancers --query 'LoadBalancers[].[LoadBalancerName,State.Code]' --output table
```

**Whether the load balancer sends requests to the instance:** `healthy` means yes. It says
`unhealthy` before the app is deployed, and for some seconds after each deploy, while the
health check catches up; during that time the guestbook's URL answers 502.

```bash
awsl elbv2 describe-target-health --target-group-arn "$(awsl elbv2 describe-target-groups --query 'TargetGroups[0].TargetGroupArn' --output text)"
```

**The HTTPS certificate:**

```bash
awsl acm list-certificates
```

## 4. From the other tools

```powershell
terraform state list        # in terraform/: every resource Terraform created
docker ps                   # the containers behind them: the emulator, the instance, the database, the console
```
