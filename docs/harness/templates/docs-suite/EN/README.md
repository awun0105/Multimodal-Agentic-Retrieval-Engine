<!-- 
DOCUMENTATION TEMPLATE: English Index
====================================
Focus: Detailed roadmap and file-by-file map for the English documentation suite.

I. AGENT EXECUTION PROTOCOL (INTERNAL GUIDANCE):
1. CONTEXT HARVESTING: Scan the `docs/EN` directory for all present documentation files.
2. PLACEHOLDER RESOLUTION: Resolve [Project Title / Name].
3. PRUNING: Remove links to files that do not exist in the project's documentation folder.
4. SURGICAL CLEANUP: Delete all italicized notes and this instruction block.

II. HUMAN CUSTOMIZATION GUIDE:
1. NAVIGATION: Ensure the "Read in this order" list reflects the actual complexity and structure of your project.
2. FILE MAP: Update the table to include any custom documentation files you've added (e.g., `security-audit.md`).
3. FINALIZATION: Verify all internal links work correctly. Delete instructional text (in *italics*) before publishing.
-->

# English Documentation

This is the definitive and comprehensive documentation suite for **[Project Title / Name]**.

Read in this order if you are new to the project:

1. [Overview](overview.md)
2. [Architecture](architecture.md)
3. [Data flows](data-flow.md)
4. [Configuration](configuration.md)
5. [Local development](local-development.md)
6. [Production deployment](deployment/setup.md)
7. [API reference](api.md)
8. [Maintenance scripts](scripts.md)
9. [Evaluation](evaluation.md)
10. [Operations](operations.md)
11. [Backup and restore](deployment/backup-restore.md)

## Files

| File | Purpose |
|---|---|
| [overview.md](overview.md) | Explains what the service does, where it fits, and what is in or out of scope. |
| [architecture.md](architecture.md) | Explains components, responsibilities, storage choices, and implementation concepts. |
| [data-flow.md](data-flow.md) | Shows end-to-end flows for search, indexing, health, metrics, and storage. |
| [configuration.md](configuration.md) | Explains `.env`, `.env.production`, settings, and credentials management. |
| [local-development.md](local-development.md) | Step-by-step local setup for coding and debugging. |
| [deployment/setup.md](deployment/setup.md) | Step-by-step production setup (Docker/VPS). |
| [api.md](api.md) | API endpoints, request/response examples, and auth behavior. |
| [scripts.md](scripts.md) | Maintenance scripts for migration, evaluation, and automation. |
| [evaluation.md](evaluation.md) | Retrieval quality criteria, benchmarks, and result templates. |
| [operations.md](operations.md) | Health, metrics, logs, job status, and common operational checks. |
| [deployment/backup-restore.md](deployment/backup-restore.md) | Procedures for state preservation and recovery validation. |

---

<div align="center">

[Back to Documentation Map](../README.md)

</div>
