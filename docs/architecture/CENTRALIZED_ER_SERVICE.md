# Centralized Entity Resolution Service

**Status**: Proposal  
**Created**: March 30, 2026  
**Authors**: Architecture Team

---

## Executive Summary

This document proposes extending the ArangoDB Entity Resolution system from a library/toolkit model into a **centralized enterprise service** — a shared infrastructure component that multiple business units use to resolve, enrich, and maintain a continuously updated knowledge graph of entities.

The core shift: instead of each team running its own ER pipeline against its own data, a central service accepts records from across the organization, resolves them against a persistent knowledge graph, and returns enriched results — including stable global identifiers, relationship context, and golden record attributes that the submitting team may not have had access to.

---

## Problem Statement

### Current Model

Today, `arango-entity-resolution` operates as a toolkit. Each deployment is standalone: a team installs the library, points it at a collection, runs a pipeline, and gets clusters. This works well for single-team, single-dataset use cases.

### Enterprise Reality

Large organizations have entity data scattered across business units:

- **Compliance** maintains KYC records with Legal Entity Identifiers (LEIs), registered addresses, and ownership hierarchies
- **Supply Chain** tracks vendors, shipping companies, and vessel registries
- **Sales** manages customer and prospect records with commercial contact data
- **Risk** monitors sanctions lists, adverse media, and politically exposed persons
- **Finance** holds counterparty records with banking and payment details

Each unit has partial information about the same real-world entities. Without a centralized resolution service:

- The same company appears as "Deutsche Bank AG", "DEUTSCHE BANK", and "DB AG" in three systems with no linkage
- A vessel's ownership chain spans four business units, none of which sees the complete picture
- Compliance identifies a sanctioned entity, but Sales continues onboarding them under a slightly different name
- Golden records are duplicated and diverge across systems

### The Opportunity

A centralized ER service acts as an **enterprise context layer** — the organization's shared understanding of "who is who." Business units submit records and get back:

1. A **stable global identifier** (internal EntityID, LEI, DUNS, IMO number, etc.)
2. The **golden record** — the best-known attributes fused from all sources
3. **Relationship context** — corporate hierarchy, shared addresses, linked vessels, beneficial owners
4. **Enrichment signals** — sanctions flags, PEP status, adverse media indicators, data quality scores

---

## Architecture

### Deployment Topology

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Centralized ER Service                           │
│                                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────────┐    │
│  │ Ingest   │  │ Resolution   │  │ Knowledge Graph             │    │
│  │ API      │→ │ Engine       │→ │ (ArangoDB)                  │    │
│  │          │  │              │  │                              │    │
│  │ REST     │  │ Blocking     │  │ Entity Documents             │    │
│  │ MCP      │  │ Similarity   │  │ Golden Records               │    │
│  │ Streaming│  │ Clustering   │  │ Relationship Edges           │    │
│  │          │  │ LLM Curation │  │ Source Provenance             │    │
│  │          │  │ Golden Record│  │ Audit Trail                   │    │
│  └──────────┘  └──────────────┘  └────────────────────────────┘    │
│                                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────────┐    │
│  │ Query    │  │ Subscription │  │ Admin                       │    │
│  │ API      │  │ Service      │  │                              │    │
│  │          │  │              │  │ Tenant Management             │    │
│  │ Lookup   │  │ Webhooks     │  │ Schema Registry               │    │
│  │ Search   │  │ CDC Stream   │  │ Policy Engine                 │    │
│  │ Traverse │  │ Event Bus    │  │ Monitoring                    │    │
│  └──────────┘  └──────────────┘  └────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
         ↑              ↑              ↑              ↑
    ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
    │ Compli- │   │ Supply  │   │ Sales   │   │ Risk    │
    │ ance    │   │ Chain   │   │         │   │         │
    └─────────┘   └─────────┘   └─────────┘   └─────────┘
```

### Interaction Patterns

#### Pattern 1: Submit-and-Resolve (Synchronous)

A business unit sends a record and gets back the resolved entity immediately.

```
POST /api/v1/resolve
{
  "source": "compliance/kyc",
  "entity_type": "company",
  "record": {
    "name": "Deutsche Bank Aktiengesellschaft",
    "country": "DE",
    "registration_id": "HRB 30000"
  },
  "options": {
    "return_golden_record": true,
    "return_relationships": true,
    "max_depth": 2
  }
}
```

Response:

```json
{
  "entity_id": "ent_00a3f7b2",
  "lei": "7LTWFZYICNSX8D621K86",
  "match_confidence": 0.97,
  "match_type": "existing",
  "golden_record": {
    "legal_name": "Deutsche Bank Aktiengesellschaft",
    "trade_names": ["Deutsche Bank", "DB"],
    "lei": "7LTWFZYICNSX8D621K86",
    "jurisdiction": "DE",
    "registered_address": "Taunusanlage 12, 60325 Frankfurt am Main",
    "status": "active",
    "sources": ["compliance/kyc", "finance/counterparty", "risk/sanctions_screening"],
    "last_verified": "2026-03-28T14:22:00Z"
  },
  "relationships": [
    {
      "type": "subsidiary_of",
      "entity_id": "ent_00a3f7b3",
      "name": "Deutsche Bank AG (parent)",
      "depth": 1
    }
  ],
  "enrichments": {
    "sanctions_status": "clear",
    "pep_associated": false,
    "data_quality_score": 0.94
  }
}
```

#### Pattern 2: Batch Ingest (Asynchronous)

A business unit submits a dataset for bulk resolution with callback notification.

```
POST /api/v1/ingest
{
  "source": "supply_chain/vendors",
  "entity_type": "company",
  "records": [...],
  "schema_mapping": {
    "name": "VENDOR_NAME",
    "address": "VENDOR_ADDRESS",
    "country": "VENDOR_COUNTRY_CODE",
    "tax_id": "VAT_NUMBER"
  },
  "callback_url": "https://supply-chain.internal/er-results",
  "options": {
    "strategy": "auto",
    "create_if_new": true,
    "return_enrichments": true
  }
}
```

#### Pattern 3: Subscribe to Entity Changes

A business unit subscribes to updates on entities it cares about.

```
POST /api/v1/subscriptions
{
  "subscriber": "risk/monitoring",
  "filter": {
    "entity_types": ["company", "person"],
    "tags": ["sanctioned", "pep", "high_risk"],
    "sources_contributed": ["compliance/kyc"]
  },
  "delivery": {
    "type": "webhook",
    "url": "https://risk.internal/entity-updates",
    "events": ["golden_record_updated", "new_relationship", "sanctions_flag_changed"]
  }
}
```

#### Pattern 4: Knowledge Graph Query

Any business unit can query the shared knowledge graph for context.

```
POST /api/v1/query
{
  "entity_id": "ent_00a3f7b2",
  "traversal": {
    "direction": "outbound",
    "edge_types": ["subsidiary_of", "beneficial_owner", "registered_at"],
    "max_depth": 3
  },
  "include": ["golden_record", "source_provenance", "quality_scores"]
}
```

---

## Knowledge Graph Schema

### Entity Documents

The knowledge graph stores resolved entities as ArangoDB documents with full provenance:

```json
{
  "_key": "ent_00a3f7b2",
  "entity_type": "company",
  "global_ids": {
    "lei": "7LTWFZYICNSX8D621K86",
    "duns": "314594417",
    "internal_id": "ent_00a3f7b2"
  },
  "golden_record": {
    "legal_name": "Deutsche Bank Aktiengesellschaft",
    "trade_names": ["Deutsche Bank", "DB", "Deutsche Bank AG"],
    "jurisdiction": "DE",
    "registered_address": {
      "street": "Taunusanlage 12",
      "city": "Frankfurt am Main",
      "postal_code": "60325",
      "country": "DE"
    },
    "status": "active",
    "entity_category": "credit_institution"
  },
  "survivorship": {
    "strategy": "most_authoritative",
    "field_sources": {
      "legal_name": {"source": "gleif/lei_registry", "confidence": 1.0},
      "registered_address": {"source": "compliance/kyc", "confidence": 0.95},
      "status": {"source": "gleif/lei_registry", "confidence": 1.0}
    }
  },
  "quality": {
    "completeness": 0.94,
    "consistency": 0.91,
    "freshness_days": 2,
    "source_count": 4,
    "last_resolved": "2026-03-28T14:22:00Z"
  },
  "tags": ["regulated_entity", "systemically_important"],
  "created": "2024-06-15T09:00:00Z",
  "updated": "2026-03-28T14:22:00Z"
}
```

### Source Records

Every record contributed by a business unit is preserved with full lineage:

```json
{
  "_key": "src_supply_chain_vendors_4821",
  "entity_id": "ent_00a3f7b2",
  "source": "supply_chain/vendors",
  "source_record_id": "VEND-4821",
  "ingested_at": "2026-03-20T11:30:00Z",
  "match_confidence": 0.93,
  "match_method": "hybrid_block_then_weighted_match",
  "original_record": {
    "VENDOR_NAME": "Deutsche Bank",
    "VENDOR_ADDRESS": "Taunusanlage 12, Frankfurt",
    "VENDOR_COUNTRY_CODE": "DE"
  }
}
```

### Relationship Edges

Relationships form the graph structure connecting entities:

| Edge Collection | Connects | Example |
|----------------|----------|---------|
| `subsidiary_of` | Company → Parent Company | DB Securities → Deutsche Bank AG |
| `beneficial_owner` | Person → Company | Individual → Shell Company |
| `registered_at` | Company → Address | Company → Registered Office |
| `operates_vessel` | Company → Vessel | Shipping Co → IMO 9334030 |
| `same_as` | Entity → Entity | Resolved duplicate linkage |
| `sourced_from` | Source Record → Entity | Provenance edge |

---

## Entity Types

The service supports multiple entity types within the same knowledge graph:

### Companies / Legal Entities

Primary identifiers: LEI, DUNS, Tax ID, Registration Number

Use cases: KYC, counterparty management, vendor deduplication, corporate hierarchy mapping

### Persons / Individuals

Primary identifiers: National ID, Passport Number, Internal Person ID

Use cases: PEP screening, beneficial ownership, sanctions matching, employee deduplication

### Vessels / Assets

Primary identifiers: IMO Number, MMSI, Call Sign, Hull Number

Use cases: Maritime compliance, sanctions screening, fleet management, port state control

### Addresses / Locations

Primary identifiers: Geocoordinates, Postal Code, UPRN

Use cases: Address normalization, registered office deduplication, geographic risk assessment

---

## Multi-Tenancy and Access Control

### Tenant Model

Each business unit is a **tenant** with:

- A unique `source` identifier (e.g., `compliance/kyc`, `supply_chain/vendors`)
- A schema mapping that translates its field names to the canonical model
- Read/write permissions defining which entity types and fields it can access
- Data contribution policies (can it create new entities, or only match against existing ones?)

### Access Control Policies

```yaml
tenants:
  compliance_kyc:
    source_id: "compliance/kyc"
    permissions:
      entity_types: [company, person]
      can_create_entities: true
      can_update_golden_record: true
      can_read_all_sources: false
      visible_fields: ["*"]
      authority_rank: 1            # highest authority for survivorship

  supply_chain_vendors:
    source_id: "supply_chain/vendors"
    permissions:
      entity_types: [company]
      can_create_entities: true
      can_update_golden_record: false
      can_read_all_sources: false
      visible_fields: ["legal_name", "address", "country", "status"]
      authority_rank: 3

  risk_monitoring:
    source_id: "risk/monitoring"
    permissions:
      entity_types: [company, person, vessel]
      can_create_entities: false
      can_update_golden_record: false
      can_read_all_sources: true
      visible_fields: ["*"]
      authority_rank: 4
```

### Survivorship Rules

When multiple sources contribute data for the same field, the golden record uses **authority-ranked survivorship**:

1. **Authoritative source wins** — the source with the highest authority rank for that field type
2. **Most complete wins** — among equal-authority sources, the most complete value
3. **Most recent wins** — among equal-completeness sources, the freshest value
4. **Conflict flagged** — when sources disagree beyond a threshold, the field is flagged for review

---

## Continuous Resolution

Unlike batch ER, a centralized service resolves **continuously** as records arrive:

### Ingest Flow

```
Record Arrives
    │
    ▼
Schema Mapping & Normalization
    │
    ▼
Blocking (find candidate matches in knowledge graph)
    │
    ├─ High confidence match (≥0.80) → Merge with existing entity
    │
    ├─ Ambiguous match (0.55–0.80) → LLM curation or human review queue
    │
    ├─ No match → Create new entity
    │
    ▼
Update Golden Record (survivorship rules)
    │
    ▼
Update Relationship Graph
    │
    ▼
Notify Subscribers
    │
    ▼
Return Enriched Result to Submitter
```

### Incremental Resolution

The existing `IncrementalResolver` class provides the foundation for this flow. It resolves a single incoming record against the knowledge graph without re-running the full batch pipeline. The centralized service wraps this in:

- **Schema mapping** — translating tenant field names to canonical fields
- **Authority-ranked golden record updates** — applying survivorship rules
- **Subscription notifications** — pushing change events to interested tenants
- **Audit logging** — recording every resolution decision with provenance

### Batch Backfill

When a new business unit onboards, its historical data is bulk-ingested via the existing `ConfigurableERPipeline`, then spliced into the live knowledge graph. The `find_duplicates` → `merge_entities` flow handles cross-source deduplication.

---

## External Data Integration

The knowledge graph can be enriched from authoritative external sources:

| Source | Data | Update Frequency |
|--------|------|------------------|
| **GLEIF** | LEI registry, corporate hierarchy, registration data | Daily delta files |
| **D&B / Moody's** | DUNS numbers, firmographic data, corporate linkage | Weekly/API |
| **OpenSanctions** | Sanctions lists, PEP databases, adverse media | Daily |
| **IMO** | Vessel registry, flag state, ownership history | Monthly |
| **National Registries** | Company house filings, tax registrations | Varies by jurisdiction |
| **Geocoding Services** | Address normalization, coordinates | On-demand |

These feeds run as scheduled ETL jobs using the existing `arangoimport` integration and `AddressERPipeline`, with their records resolved against the knowledge graph like any other source.

---

## MCP Integration

The existing MCP server evolves to support the centralized service model:

### New Tools (proposed)

| Tool | Purpose |
|------|---------|
| `submit_record` | Submit a record for resolution and get back the matched entity |
| `lookup_entity` | Look up an entity by global ID (LEI, DUNS, IMO, internal ID) |
| `traverse_relationships` | Walk the knowledge graph from an entity |
| `subscribe_entity` | Subscribe to changes on a specific entity |
| `check_sanctions` | Check an entity against sanctions/PEP enrichments |
| `onboard_source` | Register a new data source with schema mapping |

This means an AI agent connected to the MCP server can act as a **data steward** — submitting records, reviewing ambiguous matches, querying relationships, and monitoring entity changes through natural language.

---

## Use Case Scenarios

### Scenario 1: Compliance Onboarding

A KYC analyst submits a new corporate customer. The service:

1. Normalizes the company name and address
2. Finds a 0.92-confidence match against an existing entity with an LEI
3. Returns the golden record including LEI, corporate hierarchy, and sanctions status
4. The analyst now has the LEI and parent company without manual lookup
5. Supply Chain is notified that a vendor they also work with has been verified by Compliance

### Scenario 2: Vessel Sanctions Screening

Risk submits a vessel name and IMO number. The service:

1. Resolves the vessel against the maritime entity graph
2. Traverses ownership edges to find the beneficial owner
3. Cross-references the owner against sanctions lists
4. Returns the ownership chain with sanctions flags
5. Compliance is notified of the new sanctions-adjacent relationship

### Scenario 3: Vendor Deduplication Across Regions

Supply Chain in Europe and Asia both work with the same manufacturer under different trade names. The service:

1. Resolves "Siemens Energy AG" (Europe) and "Siemens Energy K.K." (Asia) to the same parent entity
2. Links them via `subsidiary_of` edges to Siemens Energy AG (parent)
3. Both regional teams see the complete vendor profile including all subsidiaries
4. Finance is alerted to consolidate payment terms

### Scenario 4: Continuous Knowledge Graph Enrichment

A nightly GLEIF delta feed adds 12,000 updated LEI records. The service:

1. Bulk-resolves them against the existing knowledge graph
2. Updates golden records where GLEIF data has higher authority
3. Creates new entities for LEIs not previously seen
4. Rebuilds corporate hierarchy edges from Level 2 relationship data
5. All business units querying those entities see updated information immediately

---

## Relationship to Current Architecture

This proposal **extends** the existing system rather than replacing it:

| Current Component | Role in Centralized Service |
|-------------------|----------------------------|
| `ConfigurableERPipeline` | Batch backfill and scheduled bulk resolution |
| `IncrementalResolver` | Real-time single-record resolution |
| `LLMMatchVerifier` / `AdaptiveLLMVerifier` | Curation of ambiguous matches |
| `AddressERPipeline` | Address normalization and resolution |
| `EmbeddingService` | Vector similarity for semantic blocking |
| MCP Server (15 tools) | AI agent interface for data stewardship |
| Advisor Tools | Strategy recommendation for new source onboarding |
| Clustering Backends (including GAE) | Large-scale entity grouping during backfill |
| Golden Record Service | Survivorship-driven record fusion |

New components needed:

| Component | Purpose |
|-----------|---------|
| **Ingest API** | REST/gRPC endpoint for submit-and-resolve |
| **Schema Registry** | Maps tenant field names to canonical model |
| **Tenant Manager** | Multi-tenant access control and authority ranking |
| **Subscription Service** | Webhook/event-bus notifications for entity changes |
| **External Feed Scheduler** | Orchestrates GLEIF, sanctions, and registry ETL |
| **Audit Store** | Immutable log of all resolution decisions |
| **Global ID Allocator** | Stable internal entity identifiers with external ID cross-reference |

---

## Implementation Phases

### Phase 1: Foundation (v4.0)

- REST API for submit-and-resolve (single record, synchronous)
- Schema registry and field mapping
- Global ID allocation and cross-reference index
- Source provenance tracking
- Tenant-scoped read/write permissions

### Phase 2: Knowledge Graph (v4.1)

- Multi-entity-type support (company, person, vessel, address)
- Relationship edge management and traversal API
- Authority-ranked survivorship for golden records
- GLEIF and sanctions feed integration
- Query API for graph traversal

### Phase 3: Continuous Operation (v4.2)

- Subscription service (webhooks, event bus)
- Streaming ingest (Kafka/CDC connector)
- Audit trail and decision log
- Dashboard and monitoring
- Rate limiting and tenant quotas

### Phase 4: Intelligence Layer (v4.3)

- AI agent data steward workflows via MCP
- Automated anomaly detection (new sanctions matches, ownership changes)
- Network analysis for hidden relationships
- Confidence scoring and data quality dashboards
- Self-service tenant onboarding via advisor tools

---

## Success Criteria

The centralized service is successful when:

1. **Multiple business units** actively submit and query entities
2. **Golden records** are measurably more complete than any single source
3. **Resolution latency** for synchronous lookups is under 500ms (p95)
4. **Batch backfill** of 1M records completes within 1 hour
5. **Sanctions and compliance signals** propagate to all relevant tenants within minutes
6. **Entity stability** — less than 0.1% of entity IDs change after initial assignment
7. **Audit trail** covers 100% of resolution decisions with source provenance

---

## Related Documents

- [System Design](DESIGN.md) — current architecture
- [PRD](../PRD.md) — product requirements and roadmap
- [API Reference](../api/API_REFERENCE.md)
- [Advanced Modules Guide](../guides/ADVANCED_MODULES_GUIDE.md)
