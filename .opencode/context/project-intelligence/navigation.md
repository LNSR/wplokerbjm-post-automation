<!-- Context: project-intelligence/navigation | Priority: critical | Version: 1.0 | Updated: 2026-06-15 -->

# Project Intelligence Navigation

**Purpose**: Navigate all context files for the WPLokerBJM Post Automation project — WordPress schema, API contracts, automation workflows, payload examples, and common errors.

---

## Structure

```
project-intelligence/
├── navigation.md
├── concepts/               # Core ideas & definitions
│   └── wordpress-schema.md
├── guides/                 # Step-by-step workflows
│   └── automation-workflows.md
├── lookup/                 # Quick reference tables
│   └── api-contracts.md
├── examples/               # Working payload examples
│   └── payload-example.md
└── errors/                 # Common issues & fixes
    └── common-errors.md
```

---

## Quick Routes

| Task | Path |
|------|------|
| **Understand WordPress CPT & MetaBox fields** | `concepts/wordpress-schema.md` |
| **Run end-to-end flyer → Telegram → WordPress** | `guides/automation-workflows.md` |
| **Find REST/GraphQL endpoint details** | `lookup/api-contracts.md` |
| **See a complete NormalizedPayload example** | `examples/payload-example.md` |
| **Troubleshoot JWT, options, or draft errors** | `errors/common-errors.md` |

---

## By Priority

**Critical** (load first):
- `concepts/wordpress-schema.md` — Core data model, taxonomies, field types
- `guides/automation-workflows.md` — End-to-end pipeline from flyer to WordPress
- `lookup/api-contracts.md` — REST endpoints, GraphQL mutations, JWT auth

**High**:
- `errors/common-errors.md` — JWT, options, draft failures
- `examples/payload-example.md` — Complete payload reference

---

## Loading Strategy

**For automation work**:
1. Load `concepts/wordpress-schema.md` — understand the data model
2. Load `lookup/api-contracts.md` — know the endpoints
3. Load `guides/automation-workflows.md` — follow the pipeline
4. Reference `examples/payload-example.md` — confirm payload shape
5. Check `errors/common-errors.md` — if anything fails

**For debugging issues**:
1. Load `errors/common-errors.md` — match symptom to solution
2. Load `lookup/api-contracts.md` — verify endpoint/credentials

---

## Related Context

- **Telegram Bot** → `../telegram-bot/navigation.md`
- **System Standards** → `../../core/context-system/navigation.md`
