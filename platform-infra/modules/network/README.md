# Network

Creates one public and one private subnet per availability zone. A shared NAT gateway minimizes fixed costs for a lab. One NAT gateway per zone avoids dependence on another zone for outbound connectivity.

VPC Flow Logs capture accepted and rejected traffic in a dedicated CloudWatch log group with 14-day retention. The publisher role trusts only VPC Flow Logs from the current AWS account and region.

Inputs are `name`, `vpc_cidr`, `az_count` (two or three) and `nat_per_az`. The module outputs `vpc_id` and `private_subnet_ids`. See [nonprod](../../envs/nonprod/main.tf) for shared NAT and [prod](../../envs/prod/main.tf) for per-zone NAT.
