# Floci: looking at what is running

Three ways to see the resources the guestbook uses in the emulator: the web console, the
emulator's own URLs, and the AWS CLI. All of them need the stack up (README, steps 2 to 5).

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

**The instances:** the app's, `guestbook`, and the VPN server, `guestbook-vpn`. For each, its
id, its state, its address on the Docker network and its subnet.

```bash
awsl ec2 describe-instances --filters Name=instance-state-name,Values=running --query "Reservations[].Instances[].[Tags[?Key=='Name']|[0].Value,InstanceId,State.Name,PrivateIpAddress,SubnetId]" --output table
```

```
+---------------+-----------------------+----------+-------------+-------------------+
|  guestbook    |  i-77b016a622103518c  |  running |  172.21.0.4 |  subnet-f24c6b23  |
|  guestbook-vpn|  i-61a1d6c61c13286b1  |  running |  172.21.0.5 |  subnet-609ee3af  |
+---------------+-----------------------+----------+-------------+-------------------+
```

Without the filter, instances that were replaced show too, for a while, as `terminated`.
The address is Docker's, not the subnet's: section 5.

**The network:** the six subnets, by tier and zone, and the four security groups.

```bash
awsl ec2 describe-subnets --filters Name=tag:Name,Values='guestbook-*' --query "Subnets[].[Tags[?Key=='Name']|[0].Value,CidrBlock,AvailabilityZone]" --output table
awsl ec2 describe-security-groups --filters Name=group-name,Values='guestbook-*' --query 'SecurityGroups[].[GroupName,GroupId]' --output table
```

```
+--------------------+----------------+--------------+
|  guestbook-app-a   |  10.0.10.0/24  |  us-east-1a  |
|  guestbook-data-b  |  10.0.21.0/24  |  us-east-1b  |
|  guestbook-public-b|  10.0.1.0/24   |  us-east-1b  |
|  ...               |                |              |
+--------------------+----------------+--------------+
```

**The VPN server's secrets:** its private key and the `tls-crypt` key, encrypted. Add
`--with-decryption` to `ssm get-parameter` to read one; the server does that at first boot.

```bash
awsl ssm describe-parameters --query 'Parameters[].[Name,Type]' --output table
```

```
+-------------------------------+----------------+
|  /guestbook/vpn/server-key    |  SecureString  |
|  /guestbook/vpn/tls-crypt-key |  SecureString  |
+-------------------------------+----------------+
```

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

What runs on the instance, and what the app wrote. An instance's container is named
`floci-aws-ec2-<instance id>`; Floci chooses that name, and has no setting to change it.
`terraform output containers` prints both, by role:

```
{
  "app" = "floci-aws-ec2-i-77b016a622103518c"
  "vpn" = "floci-aws-ec2-i-61a1d6c61c13286b1"
}
```

```powershell
docker exec floci-aws-ec2-<app id> supervisorctl status                 # gunicorn and nginx, under supervisord
docker exec floci-aws-ec2-<app id> tail /var/log/guestbook.log          # the app's output
docker exec floci-aws-ec2-<app id> readlink /opt/guestbook/current      # the release that runs
```

On the VPN server:

```powershell
docker exec floci-aws-ec2-<vpn id> supervisorctl status                 # openvpn, under supervisord
docker exec floci-aws-ec2-<vpn id> cat /var/log/openvpn-status.log      # who is connected now, and from where
docker exec floci-aws-ec2-<vpn id> tail /var/log/openvpn.log            # connections, refusals ("AUTH_FAILED", "tls-crypt unwrapping failed")
docker exec floci-aws-ec2-<vpn id> cat /var/log/vpn-user-data.log       # its first boot: installs, the keys' fetch, retries
docker exec floci-aws-ec2-<vpn id> ls /etc/openvpn/server/ccd           # who may connect: one file per name in vpn_clients
```

## 5. What Floci 2.5.0 does with instances and networks

Checked on 2026-11-22 and 2026-11-23 with this project's settings (`compose.yaml`).

**A network is recorded, not built.** Floci accepts a VPC of one's own, subnets in two zones,
an internet gateway, Elastic IPs, a NAT gateway, route tables and their routes, an S3 gateway
endpoint, a DB subnet group, and security-group rules that name another group or open a UDP
port. A load balancer in such subnets, with a security group, works: its target is
`healthy` and its listener answers. None of it changes where traffic goes:

| What | On AWS | In Floci |
|---|---|---|
| An instance's private address | From its subnet's CIDR | From the Docker network `guestbook-on-floci`, whatever the subnet says |
| Its public address | An Elastic IP or none | `127.0.0.1` when one is asked for |
| Its way out to the internet | Only through an internet or NAT gateway | Always: its container is also on Docker's default `bridge` network |
| Security groups | Enforced | Recorded only |
| RDS with `publicly_accessible = false` | Reachable from inside the VPC only | Still `aws-emulator`, from every container on the network; a second RDS instance gets port 7002 |

**Ports on the laptop.** Each instance's SSH port is published on every network interface,
one port per instance from 2200 (2200, 2201, ...). Nothing else is published for an
instance: with `FLOCI_SERVICES_EC2_PUBLISH_SECURITY_GROUP_PORTS` set to `true`, rules for
TCP and UDP ports open to `0.0.0.0/0` still published none. So a program outside the Docker
network can reach an instance only by SSH.

**A pinned subnet works.** With `ipam` and a subnet set for `guestbook-on-floci` in
`compose.yaml` (tried with `172.30.0.0/24`), Floci, RDS and the instances come up in it, and
the addresses are predictable. This project doesn't pin it: Terraform reports each
instance's address, and a pinned range could clash with another Docker network.

**A VPN client on the Docker network must route each address alone.** A route the server
pushes for the network's own subnet loses to the client container's connected route to that
subnet, so the traffic goes direct and skips the tunnel. The deploy's profile therefore
takes no pushed routes (`route-nopull`) and routes the instance's address as a `/32`;
`ansible/run-playbook.sh` checks it before the playbook runs.

**Elastic IPs, and what Terraform has to allow for:**

- An Elastic IP has the address `203.0.113.x` while it is attached to nothing, and
  `127.0.0.1` once it is. Read it from `aws_eip_association`, which gives the address after
  the attach.
- Once one is attached, the instance reports `associate_public_ip_address = true`. Writing
  `false` makes every plan replace the instance.
- Moving one to a new instance through `aws_eip`'s `instance` fails: the provider sends both
  the instance and its network interface, and Floci answers "Specify either InstanceId or
  NetworkInterfaceId, but not both". A separate `aws_eip_association` sends only the
  instance.

**A rule's peer group comes back as `000000000000/sg-...`,** the form AWS uses for another
account's group. The provider expects that form when it doesn't know its own account id,
and `versions.tf` tells it not to ask (`skip_requesting_account_id`). Every plan would change
the rule, so the rules ignore that attribute (`terraform/security-groups.tf`). Letting the
provider ask instead is worse: it then calls S3 Control, which has no emulator endpoint
here, so the call goes to real AWS (and is refused).

**Parameter Store and instance roles work.** A `SecureString` comes back decrypted with
`--with-decryption`, and as ciphertext without it. From an instance, the AWS CLI and boto3
get the role's credentials from the metadata service and read it at
`http://aws-emulator:4566`. The policy isn't enforced, like every IAM policy here.

**How a new instance is set up.** Floci starts the container, then installs with dnf what it
needs: the metadata service's proxy (it waits up to 180 seconds) and openssh-server (up to
120 seconds). Then it injects the SSH key, starts sshd, and runs the instance's `user_data`.

- **On a slow network the downloads time out, and Floci does not retry.** The instance is
  `running` but has no sshd, and Ansible gets "Connection refused" on port 22. Two instances
  started at once timed out both. The answer is a new instance:
  `terraform apply -replace=aws_instance.app`, then deploy again.
- **`user_data` runs, after Floci's own setup.** But a download that timed out may still be
  running: a `dnf` in `user_data` then waits for it and can fail on the shared package cache.
  A `user_data` script that installs packages should try again.
- **The image has no `sysctl`, `ps` or `pkill`.** A script writes to `/proc/sys/...` and reads
  `/proc` instead. The container is privileged and has `/dev/net/tun`.

**One Floci per Docker daemon.** A second Floci started on the same laptop removed this
stack's instance container the second it started. The first Floci went on reporting the
instance `running`, and the load balancer answered 502. Before starting another Floci, stop
this stack (`make destroy`). To recover, replace the instance as above.
