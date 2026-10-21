# Checkpoints

1. Implemented and tested: API skeleton, validated settings, health endpoint.
2. Implemented and tested on Neon: PostgreSQL + pgvector, SQLAlchemy and Alembic.
3. Implemented and tested: bounded PDF validation, extraction, estimated-token chunking and page provenance.
4. Implemented and verified: versioned embeddings, local upload and atomic ingestion; final suite 97 passed, including a live synthetic embedding/storage smoke test.
5. Retrieval, grounded answers, citations and unsupported questions.
6. Minimal React UI and early RAG deployment with agreed access limits.
7. Actual GitHub MCP discovery and read-only tool invocation.
8. Approved deterministic routing and bounded combined evidence workflow.
9. Focused evaluation, CI/CD, deployed smoke tests and resume-claim audit.

Pause after each checkpoint for an understanding check. Use uv exclusively for
Python dependency/environment management and execution. Keep the app/routes,
app/schemas and app/services structure. Do not introduce Ruff.

The target is two focused days, not a guarantee. Review official provider docs,
account quotas and data-use policies before integrations. Preserve the ₹0 budget.
