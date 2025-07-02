# Veterinary Clinical AI Platform – Full Requirements

## Table of Contents
1. Objectives
2. System Architecture Overview
3. Corpus Acquisition at Scale
4. Ask Service – Detailed Flow
5. Diagnose Service – Sequential Orchestrator Logic
6. High‑Quality Sample‑Case Generation & Rating Framework
7. Non‑Functional & Compliance Requirements
8. Tech‑Stack Snapshot
9. Phased Roadmap
10. Omnichannel Client Layer – Web & iOS
11. Cross‑Platform Design System
12. Client ↔ Backend Contract
13. Security & Compliance Touch‑points
14. Build, Test, Release Workflow
15. Accessibility & Internationalisation
16. Implementation Sequence Checklist
17. Key Take‑aways
18. Implementation Plan

---

## 1. Objectives

| Function | Goal | Primary User | Success KPI | Dependencies |
|----------|------|--------------|-------------|--------------|
| Ask | Instant, referenced answers to veterinary‑clinical questions | Clinicians, students | ≤ 5 s median latency; ≥ 95 % citation accuracy | Curated literature corpus; RAG stack |
| Diagnose | Interactive clinical‑decision support that iteratively questions, orders tests, then delivers a ranked differential | Practising veterinarians | ≥ 80 % correct top‑3 diagnosis on benchmark cases; < 30 s per step | Ask micro‑service; orchestrator; cost table |
| Eval Loop | Generate and score realistic test cases to measure safety, accuracy, cost | Vet expert raters | ≥ 0.8 inter‑rater kappa; weekly model release gate | Synthetic‑case pipeline; rating UI |

---

## 2. System Architecture Overview

* **UI Layer** – Web PWA and native iOS app provide Ask, Diagnose, and Case Replay modes.
* **Gateway / Orchestrator** – Dispatches calls, enforces rate limits, stores audit logs. A sequential diagnostic orchestrator mirrors the Microsoft `Path to Medical Superintelligence` pattern.
* **LLM & Tools Layer** – MedGemma‑27B‑Vet‑IT (text) and MedGemma‑4B‑Vet‑MM (multimodal) fine‑tuned on veterinary corpora. Plug‑ins: drug DB, breed ontology, price list.
* **Retrieval Layer** – Hybrid BM25 + embedding search in a vector store; evidence scorer for ranking and citation.
* **Data Lake** – Raw PDFs, PubMed XML, CAB Abstracts, conference proceedings in S3; Airflow pipelines handle ingest → OCR → chunk → embed → index.
* **Evaluation & Monitoring** – Synthetic‑case generator, MLFlow metrics, safety dashboards.

---

## 3. Corpus Acquisition at Scale

| Source | Access Method | Volume / Year | Veterinary Coverage | Notes |
|--------|--------------|--------------|--------------------|-------|
| PubMed / Europe PMC | REST + bulk FTP | ≈ 35 k | Medium | Filter with species keywords |
| CAB Abstracts | Institutional API | ≈ 10 k | High | Ag‑vet scope |
| OA papers | Unpaywall | variable | Medium | OA only |
| Conference PDFs | Web crawl | ≈ 5 k | High | ACVIM, WSAVA, IVECCS |
| University repos | OAI‑PMH | ≈ 2 k | Niche | Theses / case series |

All PDFs are converted to structured JSON via GROBID, chunked, embedded, and indexed.

---

## 4. Ask Service – Detailed Flow

1. Normalise query and embed.
2. Retrieve *k* = 40 chunks using dense + sparse fusion.
3. Re‑rank with cross‑encoder MedGemma‑27B‑re‑rank.
4. Synthesize answer with cite‑while‑generate prompt template.
5. Factuality filter: small Vet‑BERT verifier rejects low‑confidence answers.
6. Return JSON `{answer, citations[...], trace_id}`.

---

## 5. Diagnose Service – Sequential Orchestrator Logic

| Stage | Agent | Action | Tools |
|-------|-------|--------|-------|
| 0 | Intake | Parse signalment, complaint, vitals | — |
| 1 | Hypothesis | Generate differential list + priors | LLM |
| 2 | Planner | Select most informative next test | Cost table |
| 3 | Evidence | Call Ask for guidelines / prevalence | Ask API |
| 4 | Critic | Check consistency & safety | Self‑check LLM |
| 5 | Decision | Output ranked Dx, confidence, next steps | — |

Each loop limited to four tests unless cost override flag present.

---

## 6. High‑Quality Sample‑Case Generation & Rating Framework

* **Synthetic Seeds** – Few‑shot prompts create ambiguous small‑animal cases with gold diagnoses; noise injected for realism.
* **Anonymised Records** – De‑identified EHRs (e.g., CSU‑VTH dataset) supply real‑world variability.
* **Diversity Sampler** – Stratify by species, body system, and acuity.
* **Rater Platform** – React + Supabase UI; Likert scales for diagnostic accuracy, reasoning clarity, harm risk, citation quality; automatic kappa monitoring.

---

## 7. Non‑Functional & Compliance Requirements

| Category | Requirement |
|----------|-------------|
| Latency | Ask ≤ 5 s P95; Diagnose step ≤ 30 s P95 |
| Uptime | 99.5 % API availability |
| Security | SOC‑2 Type II, HIPAA, GDPR |
| Explainability | Source PDF click‑through; chain‑of‑thought log retained for audit |
| Versioning | Semantic model IDs (e.g., medgemma‑27b‑vet‑it‑v0.2) |
| Cost Guard | Budget envelope per org; orchestrator enforces spend cap |

---

## 8. Tech‑Stack Snapshot

* **Backend** – Python 3.12, FastAPI, Celery, Postgres
* **Inference** – Triton on A100/H100 or vLLM for throughput
* **Vector DB** – Weaviate with HNSW + BM25
* **Pipelines** – Airflow on Kubernetes; S3 object store; Glue catalog
* **Observability** – Prometheus, Grafana, Sentry

---

## 9. Phased Roadmap

| Quarter | Milestone | Exit Criteria |
|---------|-----------|--------------|
| Q3‑25 | Corpus ingestion; Ask v0; design system v0 | PWA loads & executes Ask query end‑to‑end |
| Q4‑25 | MedGemma vet fine‑tune; Ask v1; iOS Ask alpha | ≥ 90 % precision@5; ≥ 500 Ask sessions in TestFlight |
| Q1‑26 | Diagnose v0 (single‑shot) + PWA integration | 70 % top‑3 accuracy; web latency P95 < 6 s |
| Q2‑26 | Full sequential orchestrator; iOS Diagnose beta | 5 pilot clinics active on iOS |
| Q3‑26 | Regulatory sandbox trial | IRB‑approved study; safety ≥ 99 % |
| Q4‑26 | Commercial GA across PWA + App Store | SLA met; in‑app billing live |

---

## 10. Omnichannel Client Layer – Web & iOS

| Surface | Tech | Primary Jobs | UX Targets | Native Hooks | Offline Story |
|---------|------|--------------|-----------|--------------|---------------|
| Web PWA | React 19 + Next.js 15, Tailwind | Ask, Diagnose, Case Replay, admin dashboards | FID < 100 ms; CLS < 0.1 | Web Push, Share API | Service‑worker cache for last 50 answers & static assets |
| iOS | SwiftUI, Combine | Same plus on‑device dictation, Face ID SSO | Cold launch < 400 ms; VoiceOver AA rating | PushKit, BackgroundTasks, haptics, Camera for image upload | Core Data cache + background sync |

---

## 11. Cross‑Platform Design System

* Token library exported from Figma then compiled via Style Dictionary.
* Shared components: Ask Bar, Evidence Viewer, Diagnostic Timeline.
* Apple HIG alignment on iOS; equivalent ARIA semantics on web.

---

## 12. Client ↔ Backend Contract

* GraphQL over HTTPS; trace_id propagated for observability.
* Streaming via HTTP2 or WebSockets to render tokens in real time.
* DICOM / JPEG / PDF upload with presigned URLs and server‑side malware scan.
* OIDC → JWT auth; tokens stored in iOS Keychain or web IndexedDB.
* Rate‑limit errors surfaced with retry‑after seconds.

---

## 13. Security & Compliance Touch‑points

| Area | Guardrail |
|------|-----------|
| Transport | HSTS, TLS 1.3, PWA served over HTTPS |
| Storage | iOS Core Data in encrypted zone; web IndexedDB AES‑GCM with device‑bound key |
| Logging | PHI redacted at gateway; telemetry sampled at 5 % |
| Mobile Review | Apple App Review Guideline §5.5 (health data privacy) checklist compliance |

---

## 14. Build, Test, Release Workflow

| Stage | Web (CI/CD) | iOS |
|-------|-------------|-----|
| Static checks | ESLint, TypeScript, Lighthouse CI | SwiftLint, unit tests |
| E2E | Playwright | XCUITest |
| Artifacts | Vercel preview URLs | TestFlight builds |
| Roll‑out | Feature flags (ConfigCat) | Phased release via App Store Connect |

---

## 15. Accessibility & Internationalisation

* WCAG 2.2 AA compliance on web; Dynamic Type, VoiceOver, Increase Contrast support on iOS.
* ICU message format localisation; vet terminology glossary managed in Phrase.

---

## 16. Implementation Sequence Checklist

1. Approve tokenised design system.
2. Scaffold PWA skeleton; connect Ask API.
3. Build SwiftUI component library; integrate GraphQL code‑gen.
4. Stand‑up shared feature flag service.
5. Conduct penetration test and prepare App Store privacy report.
6. Deliver pilot clinic onboarding playbook.

---

## 17. Key Take‑aways

* Separate yet synergistic micro‑services (Ask and Diagnose) maximise reuse and speed.
* Vet‑specific data and fine‑tuned MedGemma models close domain gap for accuracy and safety.
* Continuous human‑in‑the‑loop evaluation provides rapid iteration without compromising trust.

---

## 18. Implementation Plan

### 18.1 Infrastructure Architecture

#### Core Technology Stack
* **Backend**: Python 3.12, FastAPI, PostgreSQL, Redis, Celery + RabbitMQ, Docker + Kubernetes
* **Data Infrastructure**: AWS S3, Apache Airflow on K8s, Weaviate vector DB, AWS Glue
* **ML Infrastructure**: NVIDIA Triton, vLLM, MLflow, Weights & Biases

#### System Architecture Layers
```
┌─────────────────────────────────────────────────────────┐
│                    Client Layer                         │
│         (React PWA + iOS SwiftUI App)                  │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                  API Gateway                            │
│        (Kong/AWS API Gateway + GraphQL)                 │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│              Orchestration Layer                        │
│         (FastAPI + Celery + Redis)                     │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                Services Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Ask Service  │  │   Retrieval  │  │   Inference  │ │
│  │   (RAG)      │  │   Service    │  │   Service    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                  Data Layer                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  PostgreSQL  │  │   Weaviate   │  │   S3 Data   │ │
│  │              │  │  Vector DB   │  │    Lake      │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

### 18.2 Veterinary Corpus Acquisition Pipeline

#### Data Sources Configuration
| Source | API Endpoint | Expected Volume/Year | Query Strategy |
|--------|--------------|---------------------|----------------|
| PubMed | `eutils.ncbi.nlm.nih.gov` | 35,000 | MeSH terms: veterinary, animal diseases |
| Europe PMC | `ebi.ac.uk/europepmc` | 20,000 | Filters: VET, AGRICOLA |
| CAB Abstracts | Institutional API | 10,000 | High veterinary coverage |
| Unpaywall | `api.unpaywall.org` | Variable | OA filter + DOAJ journals |
| Conferences | Web crawl | 5,000 | ACVIM, WSAVA, IVECCS, BSAVA, ECVIM |

#### ETL Pipeline Stages
1. **Discovery**: Query APIs, crawl conference sites, check for updates
2. **Acquisition**: Download PDFs/XML, validate, deduplicate by DOI
3. **Processing**: GROBID extraction, text cleaning, document chunking
4. **Enrichment**: Generate embeddings, extract species/clinical entities, quality scoring
5. **Indexing**: Update Weaviate, BM25 index, PostgreSQL metadata

#### Document Processing Configuration
* **GROBID**: Full citation consolidation, raw affiliations extraction
* **Chunking**: Semantic strategy, 512 token chunks with 50 token overlap
* **Embedding**: sentence-transformers/all-MiniLM-L6-v2, batch size 32
* **Quality Scoring**: Journal impact factor, citations, recency, veterinary relevance

---

### 18.3 MedGemma Fine-tuning Strategy

#### Model Configuration
| Model Type | Base Model | Target | Purpose |
|------------|------------|--------|---------|
| Text | MedGemma-27B | MedGemma-27B-Vet-IT | Clinical Q&A, reasoning |
| Multimodal | MedGemma-4B | MedGemma-4B-Vet-MM | Image analysis |

#### Training Configuration
* **Method**: LoRA (Low-Rank Adaptation)
* **Hardware**: 8×A100-80GB GPUs with DeepSpeed ZeRO-3
* **Hyperparameters**: 
  - LoRA rank: 64, alpha: 128
  - Batch size: 4, gradient accumulation: 8
  - Learning rate: 2e-5, warmup: 1000 steps

#### Training Phases
1. **Domain Adaptation** (2 weeks): Adapt to veterinary terminology
2. **Instruction Tuning** (3 weeks): Teach clinical reasoning patterns
3. **Safety Alignment** (1 week): Ensure safe clinical recommendations
4. **Citation Training** (1 week): Accurate source attribution

#### Training Data Structure
* **QA Pairs**: Veterinary textbooks formatted with questions, answers, citations
* **Clinical Cases**: Anonymized EHRs with signalment, history, diagnosis
* **Literature Synthesis**: Systematic reviews with queries, evidence, conclusions
* **Quality Filters**: Citation accuracy ≥ 95%, veterinary relevance ≥ 90%

---

### 18.4 Implementation Roadmap

#### Phase 1: Foundation (Weeks 1-4)
- Set up AWS infrastructure (VPC, EKS, S3)
- Deploy PostgreSQL, Redis, Weaviate
- Configure Airflow on Kubernetes
- Establish CI/CD pipelines

#### Phase 2: Data Pipeline (Weeks 5-8)
- Implement PubMed/Europe PMC crawlers
- Deploy GROBID service
- Build chunking/embedding pipeline
- Create Weaviate indexing workflows

#### Phase 3: Model Preparation (Weeks 9-12)
- Set up GPU cluster
- Prepare veterinary training datasets
- Implement LoRA fine-tuning pipeline
- Create evaluation benchmarks

#### Phase 4: Ask Service (Weeks 13-16)
- Build FastAPI backend
- Implement RAG pipeline
- Add citation validation
- Create GraphQL API layer

#### Phase 5: Frontend Development (Weeks 17-20)
- Scaffold React PWA
- Implement Ask UI components
- Add authentication
- Deploy to Vercel

#### Phase 6: Testing & Launch (Weeks 21-24)
- Security audit
- Pilot with veterinary clinics
- Performance optimization
- Production launch preparation

---

### 18.5 Key Implementation Considerations

1. **Scalability**: Horizontal scaling for inference, aggressive caching
2. **Cost Control**: Request batching, spot instances for training
3. **Data Quality**: Expert review board, automated quality checks
4. **Compliance**: HIPAA for clinical data, comprehensive audit logging
5. **Performance**: <5s latency target, streaming responses

---

*References:*
* Microsoft `The Path to Medical Superintelligence` – <https://microsoft.ai/new/the-path-to-medical-superintelligence/>
* OpenEvidence – <https://openevidence.com/>

