<!-- 
DOCUMENTATION TEMPLATE: Main Map
===============================
Focus: Global navigation and role-based reading paths for all project documentation.

I. AGENT EXECUTION PROTOCOL (INTERNAL GUIDANCE):
1. CONTEXT HARVESTING: Verify the existence of language directories (EN, VN) and core documentation files.
2. PLACEHOLDER RESOLUTION: Resolve [Project Title / Name].
3. PRUNING: Remove language links or paths if only one documentation set is available.
4. SURGICAL CLEANUP: Delete all italicized notes and this instruction block.

II. HUMAN CUSTOMIZATION GUIDE:
1. NAVIGATION: Update the folder structure diagram if your documentation is organized differently.
2. READING PATHS: Adjust the recommended paths for New Users, Developers, and Operators based on your project's specific onboarding flow.
3. FINALIZATION: Ensure the "Question Index" links to the most relevant documents for quick answers. Delete instructional text (in *italics*) before publishing.
-->

# Documentation Map

This folder is organized by language.

```text
docs/
├── README.md        # You are here
├── EN/              # Current complete documentation
├── VN/              # Vietnamese documentation
└── plans/           # Planning/internal notes, not the main user docs
```

## Language Notice

- **English**: use [EN/README.md](EN/README.md). This is the current authoritative documentation set for the **[Project Title / Name]** codebase.
- **Vietnamese**: use [VN/README.md](VN/README.md).

## Recommended Reading Paths

### New User / Stakeholder
1. [Project overview](EN/overview.md)
2. [Architecture](EN/architecture.md)
3. [Data flows](EN/data-flow.md)

### Developer
1. [Local development](EN/local-development.md)
2. [Configuration](EN/configuration.md)
3. [Architecture](EN/architecture.md)
4. [Data flows](EN/data-flow.md)

### Operator / Deployment
1. [Configuration](EN/configuration.md)
2. [Production deployment](EN/deployment/setup.md)
3. [Operations](EN/operations.md)
4. [Backup and restore](EN/deployment/backup-restore.md)

## Question Index

| Question | Read |
|---|---|
| What is this project? | [EN/overview.md](EN/overview.md) |
| How does the architecture work? | [EN/architecture.md](EN/architecture.md) |
| How does the data flow? | [EN/data-flow.md](EN/data-flow.md) |
| Which `.env` file should I use? | [EN/configuration.md](EN/configuration.md) |
| How do I run locally? | [EN/local-development.md](EN/local-development.md) |
| How do I deploy to production? | [EN/deployment/setup.md](EN/deployment/setup.md) |
| How do I monitor the service? | [EN/operations.md](EN/operations.md) |
| How do I back up and restore state? | [EN/deployment/backup-restore.md](EN/deployment/backup-restore.md) |

---

<div align="center">

[Back to Main README](../README.md)

</div>
