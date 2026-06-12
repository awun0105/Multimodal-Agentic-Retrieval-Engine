<!-- 
DOCUMENTATION TEMPLATE: Backup and Restore
==========================================
Focus: State preservation, data safety, and disaster recovery procedures.

I. AGENT EXECUTION PROTOCOL (INTERNAL GUIDANCE):
1. CONTEXT HARVESTING: Identify critical stateful components (databases, object stores, config files) and existing backup scripts or tools.
2. PLACEHOLDER RESOLUTION: Replace [bracketed] text with the exact tools and CLI commands used for dumping and restoring data.
3. PRUNING: Remove sections if the project is stateless or uses managed backups.
4. SURGICAL CLEANUP: Delete all italicized notes and this instruction block.

II. HUMAN CUSTOMIZATION GUIDE:
1. PLACEHOLDERS: Provide tested CLI examples for your project's specific database and storage backends.
2. TAILORING: Define a clear "Backup Strategy" frequency (e.g., daily, hourly).
3. FINALIZATION: Ensure recovery steps are verified. Delete instructional text (in *italics*) before publishing.
-->

# Backup and Restore

Procedures for state preservation and disaster recovery for **[Project Title / Name]**.

## Backup Strategy

- **Database**: [e.g., pg_dump daily].
- **Object Storage**: [e.g., rclone sync to S3].
- **Configuration**: [e.g., Encrypted secret vault].

## Recovery Check (Restoring)

### 1. Database Restore
```bash
# Example command
psql -U [user] [db_name] < backup.sql
```

### 2. Object Storage Restore
*Instructions for restoring binaries/files.*

## Automated Checks
*Explain any scripts or cron jobs that verify backup integrity.*

---

<div align="center">

[Back to Documentation Index](../README.md)

</div>
