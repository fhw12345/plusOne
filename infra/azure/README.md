# Azure infra notes

## Resources

| Resource | Tier | Region | Approx $/mo |
|----------|------|--------|-------------|
| Azure Database for PostgreSQL Flexible Server | Burstable B1ms | East Asia | $15 |
| (later) Azure Cache for Redis | Basic C0 | East Asia | $16 |

## Postgres setup checklist

- [ ] Create Flexible Server (Postgres 16, B1ms, 32GB storage, East Asia)
- [ ] Set admin user / password (store in 1Password)
- [ ] Configure firewall:
  - [ ] Add your dev IP
  - [ ] Add Fly.io NRT region IP ranges (or use private endpoint)
- [ ] Enable automated backups (default 7-day retention)
- [ ] Enable point-in-time recovery
- [ ] Create `plus_one` database
- [ ] Configure SSL = required
- [ ] Connection string format:
  ```
  postgresql+asyncpg://<user>:<pass>@<server>.postgres.database.azure.com:5432/plus_one?ssl=require
  ```

## Cost optimization

- Burstable B1ms is enough for development + early users
- Scale up to General Purpose D2s_v3 (~$120/mo) only when CPU > 60% sustained
- Stop server when not actively developing (Azure supports stop/start to save $$)

## Bicep / IaC (TODO)

When the infra stabilizes, codify in `infra/azure/main.bicep` so re-creation
is reproducible. For now, manual creation via Azure Portal is fine.
