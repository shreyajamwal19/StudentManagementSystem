# Cloud Deployment Plan (documented now; demo later if feasible)

The "cloud computing" part of the research is the cloud-hosted record store and application tier, with the permissioned
blockchain providing integrity verification.

## Local (current)
Docker Compose: PostgreSQL 16. Later: Spring Boot app, 4 Besu validators, React static build.

## Target cloud topology (provider-neutral; AWS example in brackets)
- **Database:** managed PostgreSQL [Amazon RDS for PostgreSQL], private subnet, encryption at rest, automated backups, TLS enforced, no public IP.
- **Application:** Spring Boot container [ECS Fargate or one EC2 VM], in a private subnet behind a load balancer/HTTPS.
- **Blockchain:** 4 Besu validator containers/VMs in a private subnet [EC2], p2p port open only between validators, JSON-RPC reachable only from the application security group.
- **Frontend:** static React build [S3 + CloudFront, or served by the same VM].
- **Secrets:** cloud secret manager [AWS Secrets Manager] for DB password, JWT secret, pseudonym pepper and Besu signer keys.
- **Monitoring:** cloud logs for application audit events and node health.

## Same code, different configuration
Only environment variables change (DB URL, Besu RPC URL, secrets). No code differences between local and cloud runs.

## Cloud demonstration plan
1. Run PostgreSQL on a managed instance and the application + Besu on one or more VMs.
2. Re-run the security experiments (T1-T6) and a reduced benchmark on the cloud setup.
3. Report cloud results separately from local results (different hardware and network latency), never mixed.
Cost and free-tier limits will decide how large the cloud run can be.
