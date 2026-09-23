# Enterprise Multi-Tenant LLM Gateway

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![Redis](https://img.shields.io/badge/Redis-7.0+-DC382D.svg)](https://redis.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15.0+-336791.svg)](https://www.postgresql.org)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-Tracing-F54A00.svg)](https://opentelemetry.io)
[![Prometheus](https://img.shields.io/badge/Prometheus-Metrics-E6522C.svg)](https://prometheus.io)
[![Grafana](https://img.shields.io/badge/Grafana-Dashboards-F46800.svg)](https://grafana.com)

A high-throughput, fault-tolerant, multi-tenant **LLM Gateway** built with **Python and FastAPI**. It acts as an intelligent, unified proxy between client applications and downstream foundation model providers (**OpenAI, Anthropic, Gemini, Groq, and local Ollama**), featuring distributed rate limiting, starvation-free priority scheduling, pre-flight budget governance, circuit breaker failover, and full OpenTelemetry/Prometheus observability.

---

## Table of Contents
- [Architecture Overview](#architecture-overview)
- [System Flow Diagrams](#system-flow-diagrams)
  - [1. High-Level System Architecture](#1-high-level-system-architecture)
  - [2. End-to-End Request Lifecycle](#2-end-to-end-request-lifecycle)
  - [3. Circuit Breaker State Machine](#3-circuit-breaker-state-machine)
  - [4. Priority Scheduling & Starvation Prevention](#4-priority-scheduling--starvation-prevention)
- [Key Features](#key-features)
- [Project Directory Layout](#project-directory-layout)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [Grafana Dashboards & Alerting](#grafana-dashboards--alerting)
- [Testing Suite](#testing-suite)
- [License](#license)

---

## Architecture Overview

The gateway is built on an asynchronous, decoupled architecture separating **authentication**, **concurrency control**, **routing logic**, and **observability**:

```
                       ┌────────────────────────────────────────┐
                       │          Client Applications           │
                       └───────────────────┬────────────────────┘
                                           │ HTTPS / Standard OpenAI Format
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   LLM GATEWAY PIPELINE                                 │
│                                                                                        │
│   ┌──────────────────────┐      ┌──────────────────────┐      ┌────────────────────┐   │
│   │   Auth & Validator   │ ───> │  Distributed Limiter │ ───> │   Priority Queue   │   │
│   │ (Postgres Budget/ACL)│      │  (Atomic Redis Lua)  │      │  (Dynamic Aging)   │   │
│   └──────────────────────┘      └──────────────────────┘      └─────────┬──────────┘   │
│                                                                         │              │
│   ┌──────────────────────┐      ┌──────────────────────┐                │              │
│   │  Observability Engine│ <─── │   Circuit Breaker    │ <──────────────┘              │
│   │ (OTel / Prometheus)  │      │ (CLOSED/OPEN/HALF-OP)│                               │
│   └──────────────────────┘      └──────────┬───────────┘                               │
│                                            │                                           │
│                                            ▼                                           │
│                        ┌───────────────────────────────────────┐                       │
│                        │      Provider Adapters (Strategy)     │                       │
│                        └───────────────────┬───────────────────┘                       │
└────────────────────────────────────────────┼───────────────────────────────────────────┘
                                             │
               ┌──────────────┬──────────────┼──────────────┬──────────────┐
               ▼              ▼              ▼              ▼              ▼
        ┌─────────────┐┌─────────────┐┌─────────────┐┌─────────────┐┌─────────────┐
        │   OpenAI    ││  Anthropic  ││Google Gemini││    Groq     ││   Ollama    │
        │  (GPT-4.1)  ││ (Claude 3.5)││(Flash 2.0)  ││ (Llama 70B) ││(Local/Edge) │
        └─────────────┘└─────────────┘└─────────────┘└─────────────┘└─────────────┘
```

---

## System Flow Diagrams

### 1. High-Level System Architecture

```mermaid
flowchart TD
    Client["Client Application"] -->|1. POST /v1/chat/completions| Ingress["FastAPI Ingress Layer"]
    
    subgraph Gateway_Core ["LLM Gateway Core Engine"]
        Ingress --> TracerStart["OpenTelemetry: Start Root Span (gateway_request)"]
        TracerStart --> Validator["Validator (validator.py)"]
        
        subgraph Auth_Storage ["PostgreSQL Storage"]
            Validator -->|Check API Key & Budget| PG[(PostgreSQL Database)]
        end
        
        Validator -->|Budget OK| RateLimiter["Rate Limiter (limiter.py)"]
        
        subgraph Redis_Engine ["Redis Concurrency Engine"]
            RateLimiter -->|Eval Token Bucket| Redis[(Redis 7.0)]
            RateLimiter -->|If Throttled: Enqueue| PriorityQueue["Aging Priority Queue"]
            PriorityQueue -->|Dynamic Aging + Atomic Claim| Redis
        end
        
        RateLimiter -->|Capacity Approved| Router["Router (router.py)"]
        Router --> CircuitBreaker["Circuit Breaker (breaker.py)"]
        CircuitBreaker -->|Check State: CLOSED/HALF_OPEN| ProviderFactory["Provider Factory"]
        
        ProviderFactory --> Adapter["Concrete Provider Adapter (base.py)"]
    end
    
    subgraph Downstream_LLMs ["External LLM Providers"]
        Adapter -->|Attempt 1..4 with Backoff| PrimaryLLM["Primary Provider (e.g. OpenAI)"]
        Adapter -.->|On Failover / Outage| FallbackLLM["Secondary Provider (e.g. Anthropic)"]
    end
    
    PrimaryLLM -->|Response / SSE Stream| Adapter
    FallbackLLM -.->|Fallback Response| Adapter
    
    Adapter --> Telemetry["Telemetry Recorder (metrics.py)"]
    Telemetry -->|Increment Counters / Histograms| PromEndpoint["/metrics HTTP Endpoint"]
    Telemetry -->|Async Mutation| PG
    Adapter -->|Return Normalized ChatResponse| Client
```

---

### 2. End-to-End Request Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor Client as Client App
    participant Gateway as FastAPI Router
    participant Validator as Validator (Postgres)
    participant Limiter as RateLimiter (Redis Lua)
    participant CB as Circuit Breaker
    participant Primary as OpenAI (Primary)
    participant Fallback as Anthropic (Secondary)
    participant Metrics as Telemetry & Prometheus

    Client->>Gateway: POST /v1/chat/completions {model: "gpt-4.1", stream: false}
    Note over Gateway: Start OTel Root Span
    
    Gateway->>Validator: Validate Team Key, ACL, and Daily/Monthly Budget
    Validator-->>Gateway: ValidationResult (Allowed = True)
    
    Gateway->>Limiter: Reserve Estimated Tokens (TOKEN_BUCKET_LUA)
    Limiter-->>Gateway: Allowed = 1 (RPM & TPM approved)
    
    Gateway->>CB: allow_request(provider="openai", model="gpt-4.1")
    CB-->>Gateway: Allowed = True (State: CLOSED)
    
    Gateway->>Primary: Execute HTTP POST (Attempt 1)
    Primary-->>Gateway: HTTP 503 Service Unavailable
    
    Note over Gateway: RetryPolicy: Exponential Backoff with Full Jitter
    Gateway->>Primary: Execute HTTP POST (Attempt 2..4)
    Primary-->>Gateway: HTTP 503 Service Unavailable (Retries Exhausted)
    
    Gateway->>CB: record_failure("openai", "gpt-4.1")
    Note over CB: 5 Failures Reached -> Trips to OPEN State!
    
    Note over Gateway: FallbackManager: Fetch same-tier healthy model
    Gateway->>Fallback: Execute HTTP POST (anthropic:claude-3-5-sonnet)
    Fallback-->>Gateway: HTTP 200 OK {content: "...", usage: {tokens: 250}}
    
    Gateway->>Limiter: Execute REFUND_LUA (Return unused reserved tokens)
    Gateway->>Metrics: Record Duration, Cost, Tokens, and Fallback Metadata
    Gateway-->>Client: HTTP 200 OK (ChatResponse with fallback_metadata attached)
```

---

### 3. Circuit Breaker State Machine

```mermaid
stateDiagram-v2
    [*] --> CLOSED: Initial Startup
    
    state CLOSED {
        [*] --> Normal_Traffic
        Normal_Traffic --> Failure_Recorded: Request exhausts retries
        Failure_Recorded --> Normal_Traffic: Failure Count < 5
    }
    
    CLOSED --> OPEN: 5 Request Failures in 60s window\n(SETEX cooldown: 60s)
    
    state OPEN {
        [*] --> Fast_Fail_Active
        Fast_Fail_Active --> Fast_Fail_Active: All incoming calls rejected in <1ms\n(Direct route to Fallback)
    }
    
    OPEN --> HALF_OPEN: Cooldown key TTL expires in Redis
    
    state HALF_OPEN {
        [*] --> Canary_Lock
        Canary_Lock --> Single_Canary_Allowed: Acquired atomic SETNX lock
        Canary_Lock --> Fast_Fail_Blocked: Lock unavailable (Wait for Canary)
    }
    
    HALF_OPEN --> CLOSED: Canary probe succeeds\n(Delete failures & reset state)
    HALF_OPEN --> OPEN: Canary probe fails\n(Restart 60s cooldown)
```

---

### 4. Priority Scheduling & Starvation Prevention

$$\text{Effective Priority} = \text{Base Priority} + \Big(\text{Aging Factor } (10.0) \times \text{Elapsed Wait Time (sec)}\Big)$$

```mermaid
gantt
    title Dynamic Priority Aging Timeline (Starvation Elimination)
    dateFormat X
    axisFormat %s sec
    
    section Request A (BATCH, Base=100)
    Arrives (P_eff = 100)           :active, 0, 5
    Ages in Queue (P_eff = 150)     :active, 5, 11
    Overtakes High Priority (P_eff = 310) :crit, 11, 21
    
    section Request B (CHAT, Base=200)
    Arrives (P_eff = 200)           :active, 0, 5
    Ages in Queue (P_eff = 250)     :active, 5, 11
    Overtakes New Stream (P_eff = 310) :crit, 11, 15
    
    section Request C (STREAM, Base=300)
    Arrives at t=5s (P_eff = 300)   :crit, 5, 11
    
    section Request D (STREAM, Base=300)
    Arrives at t=11s (P_eff = 300)  :active, 11, 16
```

---

## Key Features

### 1. Unified Multi-Provider Abstraction
* **Standardized Protocol:** Exposes an OpenAI-compatible interface (`/v1/chat/completions`) across **OpenAI, Anthropic, Gemini, Groq, and Ollama**.
* **Zero-Buffer SSE Streaming:** Real-time chunk pass-through via Python async generators (`StreamChunk`) with live token tracking.

### 2. Distributed Rate Limiting & Concurrency Control
* **Atomic Redis Lua Engine:** Rate-limit counters are evaluated in-memory using single-threaded Lua scripts (`TOKEN_BUCKET_LUA`), eliminating race conditions without database locks.
* **Dual-Tier Throttling:** Enforces both **Requests Per Minute (RPM)** and **Tokens Per Minute / Day (TPM/TPD)**.
* **Reserve-and-Refund Pattern:** Pre-flight token reservation based on estimated prompt length, with post-flight atomic refunding of unconsumed tokens via `REFUND_LUA`.

### 3. Aging-Aware Priority Scheduling
* **Tiered Base Priorities:** Categorizes traffic into `STREAM` (High = 300), `CHAT` (Medium = 200), and `BATCH` (Low = 100).
* **Dynamic Aging (+10 pts/sec):** Gradually promotes waiting jobs to higher priority, mathematically preventing starvation of batch jobs.
* **Capacity Reservation:** Protects 10–20% capacity buffers for high-priority live chat.

### 4. Multi-Tenant Governance & Pre-Flight Cost Control
* **Pre-Flight Budget Caps:** Validates team daily and monthly spend in PostgreSQL *before* calling upstream LLMs, blocking over-budget calls with HTTP 429.
* **Granular Model Pricing:** Dynamic token cost calculation engine (`cost.py`) computing exact USD cost per request.

### 5. High Availability, Retries & Fallback Routing
* **Exponential Backoff with Full Jitter:** Automatically retries transient 429/503 errors up to 3 times with randomized backoff delays to prevent the "Thundering Herd" problem.
* **Capability-Aware Fallbacks:** Automatically reroutes failed primary calls to same-tier alternative models (e.g. `gpt-4.1` -> `claude-3-5-sonnet`) with transparent `fallback_metadata`.

### 6. Distributed State-Machine Circuit Breaker
* **Redis State Machine:** Tracks provider states (`CLOSED`, `OPEN`, `HALF_OPEN`) cluster-wide.
* **Sub-Millisecond Fast-Failing:** Fast-fails requests in <1ms during `OPEN` state to protect worker threads.
* **Atomic Canary Recovery:** Enforces a single canary probe lock via Redis `SETNX` during `HALF_OPEN` to test provider recovery safely.

### 7. Proactive Hybrid Health Monitoring
* **Passive Telemetry:** Ingests live latency and error rates into a 5-minute rolling Redis window.
* **Smart Idle Active Probes:** Automatically skips active probes if real user traffic is fresh, saving thousands in synthetic polling costs.
* **4-State Model:** Classifies models as `HEALTHY`, `DEGRADED`, `DOWN`, or `RECOVERING`.

### 8. End-to-End Distributed Observability
* **OpenTelemetry Tracing:** Spans covering `authentication`, `rate_limit_check`, `circuit_breaker_check`, and `llm_api_call`.
* **Prometheus Metrics:** Exposes request rates, error rates, token throughput, USD cost, and latency histograms (P50, P95, P99) at `/metrics`.
* **3 Production Grafana Dashboards:** Pre-configured JSON dashboards for **Operations**, **Business**, and **Performance**.
* **Alertmanager Integration:** Real-time Slack notifications for error rate spikes, SLA breaches, budget caps, and open circuit breakers.

---

## Project Directory Layout

```text
d:\PROJECTS\LLM_Gateway\
├── database/
│   └── schema.sql                          # PostgreSQL schema (teams, models, budgets, audit logs)
├── project/
│   ├── cache/
│   │   └── connection.py                   # Async Redis connection pool management
│   ├── database/
│   │   ├── connection.py                   # Async PostgreSQL connection pool (asyncpg)
│   │   ├── team_repository.py              # Team budget and usage queries
│   │   ├── model_repository.py             # Model pricing & ACL repository
│   │   └── provider_repository.py          # Provider configuration
│   ├── gateway/
│   │   ├── circuit_breaker/
│   │   │   ├── breaker.py                  # Distributed Circuit Breaker state machine
│   │   │   ├── config.py                   # Thresholds, cooldowns, canary settings
│   │   │   └── repository.py               # Audit log persistence
│   │   ├── cost_per_req/
│   │   │   └── cost.py                     # Token cost calculation engine
│   │   ├── health/
│   │   │   ├── monitor.py                  # Background health check loop
│   │   │   ├── service.py                  # Health Service (Active & Passive)
│   │   │   └── metrics.py                  # 4-State rolling window evaluator
│   │   ├── providers/                      # Provider Adapters (Strategy Pattern)
│   │   │   ├── base.py                     # BaseProvider abstract base class
│   │   │   ├── openai.py                   # OpenAI provider adapter
│   │   │   ├── anthropic.py                # Anthropic Claude provider adapter
│   │   │   ├── gemini.py                   # Google Gemini provider adapter
│   │   │   ├── groq.py                     # Groq provider adapter
│   │   │   └── ollama.py                   # Local Ollama provider adapter
│   │   ├── ratelimit/
│   │   │   ├── limiter.py                  # RateLimiter orchestrator
│   │   │   ├── lua_scripts.py              # Atomic Redis Lua scripts (TOKEN_BUCKET, REFUND, CLAIM)
│   │   │   ├── priority.py                 # Priority levels & aging configs
│   │   │   ├── priority_queue.py           # Redis-backed dynamic aging queue manager
│   │   │   └── estimator.py                # Token cost estimator
│   │   ├── routing/
│   │   │   ├── router.py                   # Core Gateway Request Router
│   │   │   ├── provider_factory.py         # Provider Factory
│   │   │   ├── retry.py                    # Exponential backoff with full jitter
│   │   │   ├── fallback.py                 # Fallback Manager
│   │   │   └── tier.py                     # Model capability tier registry
│   │   ├── schemas/                        # Canonical Pydantic schemas
│   │   │   ├── request.py                  # ChatRequest
│   │   │   ├── response.py                 # ChatResponse
│   │   │   └── stream.py                   # StreamChunk & StreamResult
│   │   ├── telemetry/                      # Observability & Metrics
│   │   │   ├── tracer.py                   # OpenTelemetry distributed tracing
│   │   │   ├── metrics.py                  # Prometheus metrics registry
│   │   │   ├── attributes.py               # Standard semantic attributes
│   │   │   └── exporter.py                 # Prometheus plaintext exporter
│   │   └── validation/
│   │       ├── validator.py                # Pre-flight authentication & budget validator
│   │       └── exceptions.py               # Domain exceptions
│   ├── grafana/
│   │   └── dashboards/                     # Production JSON dashboards
│   │       ├── operations_dashboard.json   # Provider health, error rates, circuit breaker states
│   │       ├── business_dashboard.json     # Per-team spend, budget utilization, token metrics
│   │       └── performance_dashboard.json  # P50/P95/P99 latency, token throughput
│   ├── prometheus/
│   │   └── alerts.yml                      # Alert rules for Prometheus Alertmanager
│   ├── alertmanager/
│   │   └── alertmanager.yml                # Slack notification routing config
│   └── tests/                              # Comprehensive automated test suites
│       ├── test_integration_suite.py       # End-to-end multi-scenario integration suite
│       ├── test_alerting.py                # Prometheus & Alertmanager validation
│       ├── test_grafana_dashboards.py      # Grafana dashboard PromQL validator
│       ├── test_prometheus_metrics.py      # Prometheus metric export tests
│       └── test_telemetry.py               # OpenTelemetry span verification
```

---

## Getting Started

### Prerequisites
- **Python 3.11+**
- **Redis 7.0+** (Running locally on `localhost:6379`)
- **PostgreSQL 15.0+** (Running locally on `localhost:5432`)

### 1. Clone & Environment Setup
```bash
git clone https://github.com/TanmayJainModi/LLMGateway.git
cd LLMGateway

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory:
```env
# Database Configuration
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/llm_gateway

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Downstream Provider API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
GROQ_API_KEY=gsk_...
OLLAMA_API_KEY=
```

### 3. Initialize Database Schema
```bash
psql -U postgres -d llm_gateway -f database/schema.sql
```

---

## API Reference

### 1. Chat Completion (Non-Streaming)
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer <TEAM_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4.1",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain circuit breakers in 2 sentences."}
    ],
    "temperature": 0.7,
    "max_tokens": 150
  }'
```

### 2. Chat Completion (Real-Time SSE Stream)
```bash
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer <TEAM_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [
      {"role": "user", "content": "Count from 1 to 10."}
    ],
    "stream": true
  }'
```

### 3. Prometheus Metrics Scraping
```bash
curl http://localhost:8000/metrics
```

---

## Grafana Dashboards & Alerting

Import the pre-built dashboards from `project/grafana/dashboards/` into Grafana:

| Dashboard | Panels Included | Key Metrics |
| :--- | :--- | :--- |
| **Operations** | 8 Panels | Requests/sec, Error Rate %, Circuit Breaker Status Grid (`CLOSED`/`OPEN`), Fallback Rate |
| **Business** | 7 Panels | Cost in USD per Team, 24h Budget Utilization Gauges, Token Consumption (Input vs. Output) |
| **Performance** | 6 Panels | Latency Quantiles (P50, P95, P99), Gateway Internal Overhead, Token Throughput/sec |

### Active Prometheus Alert Rules:
- **`ProviderErrorRateHigh` (Critical):** Triggers if error rate > 5% for 2m.
- **`TeamApproachingBudgetCap` (Warning):** Triggers if a team reaches >= 80% of their daily budget.
- **`LatencyP99AboveSLA` (Warning):** Triggers if P99 latency exceeds 5.0s for 2m.
- **`CircuitBreakerOpened` (Critical):** Triggers instantly when a provider circuit trips to `OPEN` (`state == 2`).

---

## Testing Suite

Execute the automated test suites to verify end-to-end integration and telemetry integrity:

```powershell
# 1. Run Comprehensive End-to-End Integration Test Suite
python project/tests/test_integration_suite.py

# 2. Run Prometheus Alerting & Alertmanager Validation Suite
python project/tests/test_alerting.py

# 3. Run Grafana Dashboard PromQL Validation Suite
python project/tests/test_grafana_dashboards.py

# 4. Run Prometheus Metrics Exporter Suite
python project/tests/test_prometheus_metrics.py

# 5. Run OpenTelemetry Distributed Tracing Suite
python project/tests/test_telemetry.py
```

### Test Suite Results:
```text
======================================================================
RUNNING COMPREHENSIVE LLM GATEWAY INTEGRATION TEST SUITE
======================================================================
[SUCCESS] Concurrent Rate Limiting verified (10 accepted, 10 rejected, provider called 10 times).
[SUCCESS] Pre-call Budget Cap Enforcement verified.
[SUCCESS] Fallback Routing after Retry Exhaustion verified.
[SUCCESS] Circuit Breaker Full Lifecycle verified.
[SUCCESS] Streaming Response Integrity verified.
[SUCCESS] Full Observability Integration verified.
======================================================================
ALL 6 INTEGRATION TEST SCENARIOS PASSED SUCCESSFULLY!
======================================================================
```

---

## License
This project is open-source under the MIT License.
