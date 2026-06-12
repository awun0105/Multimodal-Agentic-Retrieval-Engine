<!-- 
DOCUMENTATION TEMPLATE: Local Development
========================================
Focus: Environment setup, dependency management, and local testing/debugging.

I. AGENT EXECUTION PROTOCOL (INTERNAL GUIDANCE):
1. CONTEXT HARVESTING: Identify required runtimes (Python, Node, etc.), dependency files, and local infrastructure setup (e.g., dev docker-compose).
2. PLACEHOLDER RESOLUTION: Replace [bracketed] text with actual CLI commands for environment creation and dependency install.
3. PRUNING: Remove sections like "Linting" if no tools are configured in the repo.
4. SURGICAL CLEANUP: Delete all italicized notes and this instruction block.

II. HUMAN CUSTOMIZATION GUIDE:
1. PLACEHOLDERS: Populate the guide with your tested setup commands (e.g., `npm install` or `pip install`).
2. TAILORING: Add specific notes about IDE configurations or local debugging tools used by your team.
3. FINALIZATION: Ensure the "Running Locally" section is simple and works for a fresh clone. Delete instructional text (in *italics*) before publishing.
-->

# Local Development

This guide explains how to set up **[Project Title / Name]** for local development, testing, and debugging.

## 1. Prerequisites
- [e.g., Python 3.11+, Node.js 18+]
- [e.g., Virtual environment tool: venv, uv, or conda]

## 2. Setup Steps
1.  **Environment**: Create and activate your virtual environment.
2.  **Dependencies**: Install development dependencies.
    ```bash
    [e.g., pip install -r requirements-dev.txt]
    ```
3.  **Local Services**: Start any local infrastructure (e.g., via `docker-compose.dev.yml`).

## 3. Running Locally
*Instructions for running the server or main process in debug mode.*

## 4. Testing
*Commands for running unit and integration tests.*

## 5. Linting and Formatting
*Instructions for using tools like Ruff, ESLint, or Prettier.*

---

<div align="center">

[Back to Documentation Index](README.md)

</div>
