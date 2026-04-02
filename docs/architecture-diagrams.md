# Dossier Review AI Assistant Architecture Diagrams

## Diagram 1: System Context (Policy-First)
```mermaid
flowchart LR
    U[Reviewer / Lead Reviewer] --> UI[Web UI]
    UI --> API[Policy API\nFastAPI]

    API --> ORCH[Orchestrator Agent]
    ORCH --> RET[Retrieval Agent]
    ORCH --> SECV[Section Validator Agent]
    ORCH --> RULES[Policy Rules Agent]
    ORCH --> VER[Evidence Verifier Agent]
    ORCH --> SYN[Decision Synthesizer Agent]

    RET --> VDB[(pgvector / BM25 Index)]
    RET --> OBJ[(MinIO Dossier Store)]
    RET --> META[(Postgres Metadata)]

    SECV --> CLS1[Section Models]
    SYN --> CLS2[Holistic Policy Model]

    ORCH --> INF[Inference Router]
    INF --> QRT[Quantized Local Runtime\nDocker Model Runner]
    INF --> SRT[Streamed-Weight Runtime\nFallback]

    RULES --> POL[(Policy Rules DB)]
    API --> AUD[(Audit Log Store)]
    API --> OBS[(Metrics / Traces)]
```

## Diagram 2: Agentic RAG Decision Flow
```mermaid
sequenceDiagram
    participant R as Reviewer
    participant UI as Web UI
    participant API as Policy API
    participant O as Orchestrator Agent
    participant RET as Retrieval Agent
    participant VAL as Section Validator Agent
    participant PR as Policy Rules Agent
    participant EV as Evidence Verifier Agent
    participant IR as Inference Router
    participant QM as Quantized Model
    participant SM as Streamed Model (Fallback)

    R->>UI: Upload dossier + query
    UI->>API: submit assessment request
    API->>O: classify intent & risk

    O->>RET: fetch context (hybrid retrieval)
    RET-->>O: evidence pack + citations

    O->>VAL: section-level checks
    VAL-->>O: presence/length/correctness scores

    O->>PR: apply hard policy constraints
    PR-->>O: allowed actions + rule hits

    O->>IR: request synthesis with context confidence
    alt standard complexity and confidence high
        IR->>QM: generate grounded draft
        QM-->>IR: response + rationale
    else high complexity or low confidence
        IR->>SM: fallback synthesis
        SM-->>IR: response + rationale
    end

    IR-->>O: candidate decision package
    O->>EV: faithfulness and citation verification
    EV-->>O: pass/fail + confidence

    alt verification pass
        O-->>API: policy recommendation + evidence
    else verification fail
        O-->>API: abstain/escalate with reason
    end

    API-->>UI: section diagnostics + holistic decision
    API->>API: persist full audit trace
```

## Diagram 3: Local Deployment Topology (Laptop-First)
```mermaid
flowchart TB
    subgraph Host[Windows Host + WSL2]
        subgraph K3D[k3d local cluster]
            UI[UI Service]
            API[Policy API]
            ORCH[Agent Orchestrator]
            RET[Retrieval Service]
            VAL[Validation Service]
            OBS[OTel Collector]
            PROM[Prometheus]
            GRAF[Grafana]
        end

        subgraph Data[Stateful Services]
            PG[(Postgres + pgvector)]
            MIN[(MinIO)]
            RED[(Redis)]
            MLF[(MLflow)]
            AUD[(Audit DB)]
        end

        subgraph Inference[Inference Runtimes]
            DMR[Docker Model Runner\nQuantized path]
            SW[Streamed-Weight Runtime\nFallback path]
        end

        CI[GitHub Actions Self-Hosted Runner]
    end

    UI --> API
    API --> ORCH
    ORCH --> RET
    ORCH --> VAL

    RET --> PG
    RET --> MIN
    ORCH --> RED
    ORCH --> MLF
    API --> AUD

    ORCH --> DMR
    ORCH --> SW

    API --> OBS
    OBS --> PROM
    PROM --> GRAF

    CI --> API
    CI --> ORCH
```

## Diagram 4: Inference Routing (Quantization + Weight Streaming)
```mermaid
flowchart LR
    IN[Request + Context Bundle] --> GATE1{Evidence confidence >= threshold?}
    GATE1 -- No --> ABST[Abstain / Escalate]
    GATE1 -- Yes --> GATE2{Complexity <= standard limit?}

    GATE2 -- Yes --> QPATH[Quantized Model Route]
    GATE2 -- No --> GATE3{Fallback Queue Available?}

    GATE3 -- No --> QPATH
    GATE3 -- Yes --> SPATH[Streamed-Weight Route]

    QPATH --> VER[Faithfulness + Citation Verifier]
    SPATH --> VER

    VER --> GATE4{Verifier pass?}
    GATE4 -- Yes --> OUT[Return policy recommendation]
    GATE4 -- No --> ABST
```

## Diagram 5: CI/CD and Quality Gates
```mermaid
flowchart LR
    DEV[Git Push / PR] --> CI[GitHub Actions]
    CI --> T1[Lint + Unit Tests]
    CI --> T2[Integration Tests]
    CI --> T3[Security Scans]
    CI --> T4[Model Quality Gates]

    T4 --> G1{Acceptance thresholds met?}
    G1 -- No --> FAIL[Block release]
    G1 -- Yes --> STG[Deploy to local staging]

    STG --> UAT[Reviewer UAT + Soak Test]
    UAT --> G2{Go-live checks pass?}
    G2 -- No --> ROL[Rollback model/image]
    G2 -- Yes --> PROD[Deploy to local production namespace]
```