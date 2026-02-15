# GitHub-KI-Integration: Architektur & Umsetzungsplan

---

## I. Annahmen & offene Punkte

**Getroffene Annahmen:**
- GitHub Enterprise Cloud im Einsatz (nicht GHES on-prem)
- Paid-Tier für GitHub Models ist auf Enterprise/Org-Ebene aktiviert
- Interne Entwickler nutzen primär Claude Code CLI und/oder VS Code
- Es gibt eine bestehende Container-Infrastruktur (Docker/K8s)
- Interner Code enthält teilweise sensible/proprietäre Logik (Datenklassifizierung nötig)
- Ziel: Claude-Modelle UND andere Modelle (GPT-4.1, Llama etc.) über GitHub-Billing nutzen
- PAT-basierte Auth ist kurzfristig akzeptabel; mittelfristig GitHub App
- Kein Self-Hosting von LLMs geplant (nur API-Routing)

**Offene Punkte (nicht blockierend):**
- Exakte Token-Unit-Preise für Claude-Modelle auf GitHub Models (nicht öffentlich dokumentiert, über GitHub-Billing-Dashboard prüfbar)
- Rate-Limits des Paid Tiers (enterprise-spezifisch, muss nach Aktivierung validiert werden)
- Ob `copilot-api`-Stil-Routing (ToS-Verstoß) vs. offizielle GitHub Models API gewünscht ist → **Annahme: nur offizielle API**

---

## II. Machbarkeit & Grenzen

### Was geht out-of-the-box

| Funktion | Status | Wie |
|----------|--------|-----|
| GitHub-Repo-Kontext in Claude Code | ✅ Funktioniert | `gh` CLI ist built-in, Git-Ops nativ |
| Repo-Zugriff via MCP | ✅ Funktioniert | `github/github-mcp-server` (77 Tools, 18 Toolsets) |
| PR-Reviews via Claude Code | ✅ Funktioniert | `/code-review` Plugin oder `claude-code-action` |
| Claude-Modelle über GitHub Models API | ✅ Verfügbar | `anthropic/claude-4-sonnet`, `anthropic/claude-3.5-haiku` etc. |
| OpenAI-kompatibles API-Format | ✅ Alle Modelle | GitHub normalisiert alle Provider auf OpenAI-Format |
| Billing über GitHub Enterprise | ✅ Möglich | Token-Unit-Pricing ($0.00001/Token-Unit), Org-Budget-Caps |
| Org-attributierte Abrechnung | ✅ Möglich | Endpoint `/orgs/{org}/inference/chat/completions` |

### Was NICHT geht

| Funktion | Status | Warum / Alternative |
|----------|--------|---------------------|
| Direkte Anthropic-API-Abrechnung über GitHub | ❌ Geht nicht | Separate Billing-Systeme; Alternative: GitHub Models API nutzen (Claude dort verfügbar) |
| Claude Code UI nativ auf GitHub Models zeigen | ❌ Kein nativer Support | Alternative: Proxy (LiteLLM) der `ANTHROPIC_BASE_URL` überschreibt |
| Anthropic Messages-API-Format auf GitHub Models | ❌ Nur OpenAI-Format | Alternative: LiteLLM übersetzt Anthropic ↔ OpenAI |
| GitHub Enterprise Server (on-prem) + Remote MCP | ❌ Nur Cloud | Alternative: Docker-basierter MCP-Server mit `GITHUB_HOST` |
| Exakte Feature-Parität (Extended Thinking, Caching) | ⚠️ Teilweise | GitHub Models normalisiert; Provider-spezifische Features gehen ggf. verloren |

---

## III. Optionenmatrix

| Kriterium | Option 1: Claude + MCP für Repos | Option 2: LiteLLM Proxy → GitHub Models | Option 3: MCP + Proxy kombiniert |
|-----------|----------------------------------|------------------------------------------|----------------------------------|
| **Beschreibung** | Claude Code mit Anthropic-Billing + GitHub MCP Server für Repo-Zugriff | LiteLLM-Proxy übersetzt Anthropic-API → GitHub Models API. Billing läuft über GitHub. | Option 1 + 2 kombiniert: MCP für Repo-Tooling, LiteLLM für Modell-Routing über GitHub |
| **Modell-Billing** | Anthropic direkt | GitHub Enterprise ✅ | GitHub Enterprise ✅ |
| **Repo-Zugriff** | ✅ Voll (77 MCP-Tools) | ❌ Kein Repo-Zugriff (nur Modell-Proxy) | ✅ Voll (77 MCP-Tools) |
| **Modell-Auswahl** | Nur Claude (Anthropic) | Alle GitHub-Models (Claude, GPT, Llama, Gemini, Grok) | Alle GitHub-Models + MCP-Tools |
| **Aufwand Setup** | 🟢 Gering (1-2 Tage) | 🟡 Mittel (3-5 Tage) | 🟡 Mittel (5-8 Tage) |
| **Aufwand Betrieb** | 🟢 Gering (MCP-Server) | 🟡 Mittel (Proxy + Monitoring) | 🟡 Mittel (Proxy + MCP + Monitoring) |
| **Enterprise-Security** | 🟡 PAT-Management nötig | 🟢 Zentrale Key-Verwaltung im Proxy | 🟢 Zentrale Key-Verwaltung + feingranulare Tool-ACLs |
| **Audit & Compliance** | 🟡 GitHub Audit Logs + Anthropic Logs (getrennt) | 🟢 Zentral via LiteLLM (Langfuse/Datadog) + GitHub Billing | 🟢 Zentral + MCP-Tool-Audit |
| **PII-Schutz** | ❌ Kein eingebauter Filter | 🟢 Presidio/Guardrails integrierbar | 🟢 Presidio + MCP-Readfilter |
| **Vendor Lock-in** | 🔴 Anthropic | 🟢 Multi-Provider, austauschbar | 🟢 Multi-Provider + standardisiertes Tooling |
| **Risiko** | 🟢 Gering (bewährter Stack) | 🟡 Format-Translation kann Edge Cases haben | 🟡 Komplexität, aber gut abgesichert |
| **Empfehlung** | Quick-Win / PoC | Produktiv wenn nur Modell-Routing nötig | **✅ Empfohlen für Enterprise** |

---

## IV. Empfohlene Zielarchitektur (Option 3)

### Textbeschreibung

Die Architektur besteht aus drei Schichten:
1. **Client-Schicht**: Claude Code CLI / VS Code mit konfiguriertem `ANTHROPIC_BASE_URL`
2. **Gateway-Schicht**: LiteLLM Proxy (übersetzt Anthropic-API → OpenAI-kompatibel, routet zu GitHub Models)
3. **Tool-Schicht**: GitHub MCP Server (Repo-Zugriff, PR-Management, Code-Suche)

### ASCII-Architekturdiagramm

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DEVELOPER WORKSTATION                        │
│                                                                     │
│  ┌──────────────┐     ┌──────────────────┐                         │
│  │  Claude Code  │────▶│  MCP: GitHub     │◀── PAT (repo, models)  │
│  │  CLI / VSCode │     │  (77 Tools)      │──▶ api.github.com      │
│  └──────┬───────┘     └──────────────────┘                         │
│         │ ANTHROPIC_BASE_URL                                        │
│         │ = https://ai-gateway.internal:4000                        │
└─────────┼───────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    INTERNAL NETWORK (K8s / Docker)                   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    LiteLLM Proxy Gateway                      │   │
│  │                    (ai-gateway.internal:4000)                 │   │
│  │                                                               │   │
│  │  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │   │
│  │  │  Auth    │  │ Rate     │  │ PII      │  │ Audit        │  │   │
│  │  │  (JWT/   │  │ Limiter  │  │ Redaction│  │ Logger       │  │   │
│  │  │  API-Key)│  │ (Budget) │  │(Presidio)│  │(Langfuse/DD) │  │   │
│  │  └────┬────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘  │   │
│  │       └─────────────┴─────────────┴───────────────┘           │   │
│  │                          │                                    │   │
│  │              ┌───────────┴───────────┐                        │   │
│  │              │  Format Translation   │                        │   │
│  │              │  Anthropic ↔ OpenAI   │                        │   │
│  │              └───────────┬───────────┘                        │   │
│  └──────────────────────────┼────────────────────────────────────┘   │
│                             │                                        │
│  ┌──────────────────────────┼────────────────────────────────────┐   │
│  │              Model Router (config.yaml)                        │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐  │   │
│  │  │claude-sonnet │ │ gpt-4.1      │ │ llama-4-scout        │  │   │
│  │  │→ github/     │ │→ github/     │ │→ github/             │  │   │
│  │  │anthropic/    │ │openai/       │ │meta/                 │  │   │
│  │  │claude-4-son..│ │gpt-4.1      │ │llama-4-scout         │  │   │
│  │  └──────────────┘ └──────────────┘ └──────────────────────┘  │   │
│  └──────────────────────────┼────────────────────────────────────┘   │
│                             │                                        │
│  ┌──────────────────────────┼───────────────────────────────────┐    │
│  │            Presidio Analyzer + Anonymizer                     │    │
│  │            (presidio-analyzer:5001, presidio-anonymizer:5002) │    │
│  └──────────────────────────┼───────────────────────────────────┘    │
│                             │                                        │
└─────────────────────────────┼────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    GITHUB CLOUD (External)                           │
│                                                                     │
│  ┌───────────────────────┐    ┌─────────────────────────────────┐   │
│  │ models.github.ai      │    │ api.github.com                  │   │
│  │ /inference/chat/      │    │ (Repos, PRs, Issues, Actions)   │   │
│  │ completions           │    │                                 │   │
│  │                       │    │ Audit Logs → SIEM Streaming     │   │
│  │ Billing: GitHub Org   │    │                                 │   │
│  └───────────────────────┘    └─────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Auth-Konzept

| Komponente | Auth-Typ | Token/Scope | Rotation |
|------------|----------|-------------|----------|
| LiteLLM Proxy (Client→Proxy) | JWT oder API-Key | Pro Entwickler/Team via LiteLLM Virtual Keys | 90 Tage |
| LiteLLM → GitHub Models | Fine-grained PAT | `models:read` (Account Permission) | 90 Tage, Vault-managed |
| MCP GitHub Server | Fine-grained PAT | `repo:read`, `issues:read`, `pull_requests:read+write`, `actions:read` | 90 Tage, Vault-managed |
| Kurzfristig (PoC) | Classic PAT | `repo`, `read:org` | 30 Tage |
| Mittelfristig | GitHub App (Installation Token) | Org-Level, per-Repo Permissions | Auto-Rotation (1h) |

**Secret-Handling:**
- Secrets in HashiCorp Vault / K8s Secrets (sealed-secrets oder external-secrets-operator)
- Niemals PATs in `.env`-Files im Repo
- LiteLLM unterstützt `os.environ/VAR_NAME` Syntax in config.yaml

### Netzwerk & Deployment

```yaml
# K8s Namespace: ai-gateway
Components:
  - litellm-proxy (Deployment, 2+ Replicas, HPA)
  - presidio-analyzer (Deployment, 1+ Replica)
  - presidio-anonymizer (Deployment, 1+ Replica)
  - redis (StatefulSet, für Caching + Rate-Limiting)

Ingress:
  - ai-gateway.internal:4000 (nur internes Netz, kein öffentlicher Zugang)
  - TLS-Terminierung am Ingress Controller
  - mTLS zwischen Services optional

Egress:
  - Nur zu models.github.ai:443 und api.github.com:443
  - Network Policy: deny-all + explizite allow-list
```

### Datenklassifizierung

| Klassifizierung | Beschreibung | Darf an GitHub Models? | Maßnahme |
|-----------------|-------------|------------------------|----------|
| PUBLIC | Open-Source-Code, Docs | ✅ Ja | Keine Einschränkung |
| INTERNAL | Interner Code ohne Secrets | ✅ Ja, mit PII-Redaction | Presidio pre_call Filter |
| CONFIDENTIAL | Code mit Business-Logik | ⚠️ Nur mit Freigabe | Repo-Allowlist im MCP-Server (`--read-only`) |
| RESTRICTED | Secrets, Keys, PII, Credentials | ❌ Nein | Secret-Detection blockiert Request |

---

## V. Schritt-für-Schritt Umsetzungsplan

### Milestone 1: PoC / Quick-Win (Woche 1-2)

| # | Task | Owner | DoD |
|---|------|-------|-----|
| 1.1 | GitHub Models Paid-Tier auf Org aktivieren, Budget-Cap setzen | Platform/Admin | Budget-Alert bei 80% konfiguriert |
| 1.2 | Fine-grained PAT erstellen (`models:read`) | Entwickler | PAT in Vault gespeichert |
| 1.3 | LiteLLM lokal starten mit GitHub-Models-Config | Entwickler | `curl localhost:4000/v1/messages` liefert Antwort von Claude via GitHub |
| 1.4 | Claude Code mit `ANTHROPIC_BASE_URL=http://localhost:4000` testen | Entwickler | Claude Code funktioniert, Billing im GitHub-Dashboard sichtbar |
| 1.5 | GitHub MCP Server (Docker) lokal starten, in Claude Code einbinden | Entwickler | `claude mcp list` zeigt Server, Repo-Tools funktionieren |

### Milestone 2: Enterprise-Gateway (Woche 3-5)

| # | Task | Owner | DoD |
|---|------|-------|-----|
| 2.1 | K8s-Namespace + Deployment-Manifeste erstellen | Platform | `kubectl get pods -n ai-gateway` zeigt alle Pods Running |
| 2.2 | LiteLLM Proxy deployen (2 Replicas, HPA) | Platform | Health-Check `/health` antwortet 200 |
| 2.3 | Redis für Caching/Rate-Limiting deployen | Platform | LiteLLM connected to Redis (Logs) |
| 2.4 | Ingress + TLS (internes Cert) konfigurieren | Platform | `curl https://ai-gateway.internal:4000/health` = 200 |
| 2.5 | Virtual Keys für Teams erstellen | Platform | Je Team eigener API-Key mit Budget-Limit |
| 2.6 | Network Policies (Egress nur GitHub) | Platform | `kubectl describe netpol -n ai-gateway` zeigt Regeln |
| 2.7 | Observability: Langfuse oder Datadog Integration | Platform | Dashboard zeigt Requests, Tokens, Kosten pro Team |

### Milestone 3: Security-Hardening (Woche 5-7)

| # | Task | Owner | DoD |
|---|------|-------|-----|
| 3.1 | Presidio Analyzer + Anonymizer deployen | Security | PII-Test: SSN/Email im Prompt wird maskiert |
| 3.2 | LiteLLM Guardrails konfigurieren (pre_call + post_call) | Security | Guardrail-Logs zeigen geblockte/maskierte Inhalte |
| 3.3 | Secret-Detection aktivieren | Security | API-Keys in Prompts werden geblockt |
| 3.4 | GitHub App erstellen (statt PAT) | Platform | Installation Tokens rotieren automatisch |
| 3.5 | Repo-Allowlist im MCP-Server (`GITHUB_TOOLSETS`, `--read-only`) | Security | Nur freigegebene Repos lesbar, kein Schreibzugriff |
| 3.6 | Audit-Log-Streaming zu SIEM konfigurieren | Security | GitHub Audit Events + LiteLLM Logs fließen ins SIEM |

### Milestone 4: Rollout & Dokumentation (Woche 7-8)

| # | Task | Owner | DoD |
|---|------|-------|-----|
| 4.1 | Developer-Onboarding-Guide erstellen | DevRel | Docs: Setup in < 10 Min möglich |
| 4.2 | `.mcp.json` Template für Projekte bereitstellen | Platform | Teams können MCP per Commit-File nutzen |
| 4.3 | Managed MCP Config für Org deployen | Platform | `/etc/claude-code/managed-mcp.json` auf Dev-Machines |
| 4.4 | Load-Test (k6/locust) | QA | Gateway hält 50 concurrent requests bei < 500ms P95 Overhead |
| 4.5 | Rollout an Pilotteam (5-10 Devs) | DevRel | Feedback gesammelt, keine Blocker |
| 4.6 | Rollout an alle Entwickler | DevRel | Alle Teams nutzen Gateway |

### Definition of Done (Gesamtprojekt)

- [ ] Alle Modell-Aufrufe laufen über GitHub-Billing (verifiziert im GitHub Billing Dashboard)
- [ ] Kein Entwickler hat direkte Provider-API-Keys
- [ ] PII/Secrets werden vor dem Senden an LLM maskiert
- [ ] Audit-Trail: Jeder Request ist nachvollziehbar (Wer, Wann, Welches Modell, Token-Count)
- [ ] Budget-Alerts sind konfiguriert und getestet
- [ ] MCP-Repo-Zugriff ist auf freigegebene Repos beschränkt
- [ ] Gateway-Uptime > 99.5% über 2 Wochen Pilotbetrieb
- [ ] Developer-Onboarding dauert < 10 Minuten

---

## VI. Risiken & Mitigations

| # | Risiko | Eintrittswahrscheinlichkeit | Impact | Mitigation |
|---|--------|---------------------------|--------|------------|
| R1 | Format-Translation verliert Features (Extended Thinking, Caching) | Mittel | Mittel | Akzeptierte Einschränkung; Feature-Matrix dokumentieren; Fallback auf Anthropic-Direct für Power-User |
| R2 | GitHub Models Rate-Limits reichen nicht | Niedrig | Hoch | Budget-Cap hochsetzen; GitHub Enterprise Support kontaktieren; Load-Test vor Rollout |
| R3 | PAT-Leak / Token-Kompromittierung | Niedrig | Hoch | Vault-managed, 90d Rotation, GitHub App als Ziel; Secrets nie in Config-Files |
| R4 | LiteLLM-Proxy Ausfall / Single Point of Failure | Niedrig | Hoch | 2+ Replicas, HPA, Health-Checks, PDB; Fallback: Entwickler können temporär direkt Anthropic nutzen |
| R5 | Sensible Daten an LLM gesendet | Mittel | Hoch | Presidio pre_call, Secret-Detection, Repo-Allowlist, Developer-Schulung |
| R6 | GitHub Models depreciert/ändert API | Niedrig | Mittel | LiteLLM abstrahiert; Config-Änderung reicht bei API-Migration |
| R7 | Kosten-Explosion (unkontrollierte Nutzung) | Mittel | Mittel | Budget-Caps auf Org + Team-Ebene, Alerts bei 80%, Virtual Keys mit Limits |
| R8 | Prompt-Injection über MCP-Tool-Outputs | Mittel | Mittel | Output-Sanitization, `MAX_MCP_OUTPUT_TOKENS` begrenzen, Code-Review der MCP-Tool-Nutzung |

---

## VII. SONNET IMPLEMENTATION BRIEF

### Tech-Stack-Empfehlung: Python/FastAPI

**Begründung:**
- LiteLLM ist Python-nativ → kein Wrapper/Bridging nötig
- Presidio (PII-Erkennung) ist Python-nativ
- FastAPI für Custom-Middleware (falls LiteLLM nicht ausreicht)
- Deployment: LiteLLM hat offizielles Docker-Image (`ghcr.io/berriai/litellm:main-latest`)
- Ökosystem: Langfuse, Guardrails AI, alle relevanten Libraries sind Python-first

> Node/TypeScript wäre nur bei Custom-Proxy-Entwicklung von Grund auf sinnvoller. Da wir LiteLLM als fertiges Gateway nutzen, ist Python der natürliche Fit.

---

### Exakte Requirements

#### Endpoints (LiteLLM Proxy)

| Endpoint | Methode | Beschreibung | Auth |
|----------|---------|-------------|------|
| `/v1/messages` | POST | Anthropic Messages API (primär für Claude Code) | Bearer Token (Virtual Key) |
| `/v1/chat/completions` | POST | OpenAI-kompatibel (für andere Tools) | Bearer Token (Virtual Key) |
| `/health` | GET | Liveness/Readiness Probe | Keine |
| `/key/generate` | POST | Virtual Key erstellen | Master Key |
| `/key/info` | GET | Key-Info abrufen | Master Key |
| `/spend/logs` | GET | Kosten-Logs abrufen | Master Key |
| `/team/new` | POST | Team erstellen | Master Key |

#### Request/Response-Formate

**Anthropic-Format (Client → Proxy):**
```json
POST /v1/messages
{
  "model": "claude-sonnet",
  "max_tokens": 4096,
  "system": "You are a helpful coding assistant.",
  "messages": [
    {"role": "user", "content": "Explain this function: ..."}
  ],
  "stream": true
}
```

**OpenAI-Format (Proxy → GitHub Models):**
```json
POST https://models.github.ai/inference/chat/completions
{
  "model": "anthropic/claude-4-sonnet",
  "max_completion_tokens": 4096,
  "messages": [
    {"role": "system", "content": "You are a helpful coding assistant."},
    {"role": "user", "content": "Explain this function: ..."}
  ],
  "stream": true
}
```

**Response (GitHub → Proxy → Client, übersetzt zurück zu Anthropic-Format):**
```json
{
  "id": "msg_abc123",
  "type": "message",
  "role": "assistant",
  "content": [{"type": "text", "text": "This function..."}],
  "model": "claude-sonnet",
  "stop_reason": "end_turn",
  "usage": {"input_tokens": 150, "output_tokens": 300}
}
```

---

### Konfigurationsdateien

#### `config.yaml` (LiteLLM)

```yaml
model_list:
  # Claude-Modelle via GitHub Models
  - model_name: "claude-sonnet"
    litellm_params:
      model: "github/anthropic/claude-4-sonnet"
      api_key: "os.environ/GITHUB_MODELS_PAT"
      api_base: "https://models.github.ai/inference"

  - model_name: "claude-haiku"
    litellm_params:
      model: "github/anthropic/claude-3.5-haiku"
      api_key: "os.environ/GITHUB_MODELS_PAT"
      api_base: "https://models.github.ai/inference"

  # Weitere Modelle
  - model_name: "gpt-4.1"
    litellm_params:
      model: "github/openai/gpt-4.1"
      api_key: "os.environ/GITHUB_MODELS_PAT"
      api_base: "https://models.github.ai/inference"

  - model_name: "llama-4-scout"
    litellm_params:
      model: "github/meta/llama-4-scout"
      api_key: "os.environ/GITHUB_MODELS_PAT"
      api_base: "https://models.github.ai/inference"

litellm_settings:
  drop_params: true                    # Ignoriere unbekannte Parameter statt Error
  set_verbose: false
  cache: true
  cache_params:
    type: redis
    host: "os.environ/REDIS_HOST"
    port: 6379
    ttl: 3600

general_settings:
  master_key: "os.environ/LITELLM_MASTER_KEY"
  database_url: "os.environ/DATABASE_URL"   # PostgreSQL für Key/Spend-Tracking
  otel_exporter: "otlp"                     # OpenTelemetry
  alerting:
    - slack
  alerting_args:
    slack_webhook_url: "os.environ/SLACK_WEBHOOK"
    budget_alerts: true

guardrails:
  - guardrail_name: "pii-masking"
    litellm_params:
      guardrail: presidio
      mode: "pre_call"
      api_base: "http://presidio-analyzer:5001"
    pii_entities_config:
      CREDIT_CARD: "MASK"
      EMAIL_ADDRESS: "MASK"
      PHONE_NUMBER: "MASK"
      US_SSN: "MASK"
      IBAN_CODE: "MASK"
      DE_ID: "MASK"
    presidio_ad_hoc_recognizers:
      - name: "api_key_recognizer"
        supported_language: "en"
        patterns:
          - name: "github_pat"
            regex: "ghp_[A-Za-z0-9_]{36}"
            score: 0.95
          - name: "generic_api_key"
            regex: "(?i)(sk-|api[_-]?key|token)[\\s=:]+['\"]?[A-Za-z0-9\\-_]{20,}"
            score: 0.85
    presidio_filter_scope: "both"
```

#### `.env` (Beispiel)

```bash
# === GitHub Models ===
GITHUB_MODELS_PAT=github_pat_xxxxxxxxxxxxxxxxxxxx
# Fine-grained PAT mit Scope: models:read (Account Permission)

# === LiteLLM ===
LITELLM_MASTER_KEY=sk-litellm-master-CHANGE-ME-IN-PRODUCTION
DATABASE_URL=postgresql://litellm:password@postgres:5432/litellm
REDIS_HOST=redis

# === Observability ===
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxx
LANGFUSE_HOST=https://langfuse.internal
SLACK_WEBHOOK=https://hooks.slack.com/services/xxx/xxx/xxx

# === GitHub MCP Server ===
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
# Fine-grained PAT mit Scopes: repo:read, issues:read, pull_requests:read+write

# === Claude Code (Developer Workstation) ===
ANTHROPIC_BASE_URL=https://ai-gateway.internal:4000
ANTHROPIC_AUTH_TOKEN=sk-team-frontend-xxxxxxxx
```

#### `.mcp.json` (Projekt-Root, für Team-Sharing)

```json
{
  "mcpServers": {
    "github": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
        "--read-only",
        "ghcr.io/github/github-mcp-server"
      ],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_MCP_PAT}",
        "GITHUB_TOOLSETS": "repos,issues,pull_requests,code_security"
      }
    }
  }
}
```

#### `docker-compose.yaml` (PoC / lokale Entwicklung)

```yaml
version: "3.9"

services:
  litellm:
    image: ghcr.io/berriai/litellm:main-latest
    ports:
      - "4000:4000"
    volumes:
      - ./config.yaml:/app/config.yaml
    environment:
      - GITHUB_MODELS_PAT=${GITHUB_MODELS_PAT}
      - LITELLM_MASTER_KEY=${LITELLM_MASTER_KEY}
      - DATABASE_URL=postgresql://litellm:litellm@postgres:5432/litellm
      - REDIS_HOST=redis
    depends_on:
      - postgres
      - redis
    command: ["--config", "/app/config.yaml", "--port", "4000"]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4000/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: litellm
      POSTGRES_USER: litellm
      POSTGRES_PASSWORD: litellm
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redisdata:/data

  presidio-analyzer:
    image: mcr.microsoft.com/presidio-analyzer:latest
    ports:
      - "5001:5001"

  presidio-anonymizer:
    image: mcr.microsoft.com/presidio-anonymizer:latest
    ports:
      - "5002:5002"

volumes:
  pgdata:
  redisdata:
```

---

### Beispiel-Requests (curl)

#### 1. Health-Check

```bash
curl https://ai-gateway.internal:4000/health
# → {"status": "healthy"}
```

#### 2. Anthropic Messages API (wie Claude Code es nutzt)

```bash
curl -X POST https://ai-gateway.internal:4000/v1/messages \
  -H "Authorization: Bearer sk-team-frontend-xxxxxxxx" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-sonnet",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "Was ist der Unterschied zwischen async und await in Python?"}
    ]
  }'
```

#### 3. OpenAI-kompatibel (für andere Tools)

```bash
curl -X POST https://ai-gateway.internal:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-team-frontend-xxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4.1",
    "messages": [
      {"role": "user", "content": "Explain Kubernetes NetworkPolicies"}
    ],
    "max_tokens": 1024
  }'
```

#### 4. Virtual Key erstellen (Admin)

```bash
curl -X POST https://ai-gateway.internal:4000/key/generate \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "team_id": "team-frontend",
    "max_budget": 100.0,
    "budget_duration": "30d",
    "models": ["claude-sonnet", "claude-haiku", "gpt-4.1"],
    "metadata": {"team": "frontend", "env": "production"}
  }'
```

#### 5. Kosten abfragen

```bash
curl "https://ai-gateway.internal:4000/spend/logs?start_date=2026-02-01&end_date=2026-02-15" \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY}"
```

---

### Security-Checkliste

#### Token & Auth (OWASP A07: Identification and Authentication Failures)
- [ ] Fine-grained PATs mit minimalen Scopes (`models:read` für Gateway, `repo:read` für MCP)
- [ ] PATs in Vault/K8s-Secrets, nie in Code oder `.env`-Files im Repo
- [ ] PAT-Rotation alle 90 Tage (automatisiert)
- [ ] Mittelfristig: GitHub App mit auto-rotierenden Installation Tokens (1h Lifetime)
- [ ] LiteLLM Virtual Keys pro Team (nicht pro User), Budget-limited
- [ ] Master Key nur für Admins, separater Rotation-Zyklus

#### Input Validation (OWASP A03: Injection)
- [ ] Presidio pre_call: PII-Erkennung für DE/EN (SSN, IBAN, Email, Telefon, Kreditkarte)
- [ ] Custom Recognizer: GitHub PATs (`ghp_*`), API-Keys, Passwort-Patterns
- [ ] Secret-Detection für Code-Snippets in Prompts
- [ ] `max_tokens` Limit enforced (verhindert unbegrenzte Kosten)
- [ ] Request-Size-Limit am Ingress (z.B. 1MB)

#### SSRF & Path Traversal (OWASP A10: Server-Side Request Forgery)
- [ ] Network Policy: Proxy darf nur zu `models.github.ai:443` und `api.github.com:443`
- [ ] MCP-Server im `--read-only` Modus
- [ ] MCP `GITHUB_TOOLSETS` auf benötigte Toolsets beschränkt
- [ ] Kein User-kontrollierter `api_base` (fest in config.yaml)
- [ ] Keine dynamische URL-Komposition aus User-Input

#### Logging & Monitoring (OWASP A09: Security Logging and Monitoring Failures)
- [ ] Alle Requests geloggt: User-ID, Modell, Token-Count, Kosten, Timestamp
- [ ] **KEINE** Prompt-Inhalte in Logs (nur Metadaten) — oder Presidio `logging_only` Mode
- [ ] **KEINE** API-Keys/Secrets in Logs (Regex-Filter in Log-Pipeline)
- [ ] Budget-Alerts bei 80% und 95%
- [ ] Anomalie-Erkennung: ungewöhnlich hohe Token-Counts pro User
- [ ] GitHub Audit-Log-Streaming zu SIEM aktiviert

#### Prompt Injection Mitigations
- [ ] System-Prompts vom User-Input separiert (LiteLLM macht dies by design)
- [ ] MCP-Tool-Outputs als potentiell untrusted behandeln (`MAX_MCP_OUTPUT_TOKENS=25000`)
- [ ] Guardrails post_call: Output auf sensible Daten scannen
- [ ] Keine automatische Code-Ausführung aus LLM-Responses ohne Review

#### Infrastructure (OWASP A05: Security Misconfiguration)
- [ ] TLS überall (Client→Proxy, Proxy→GitHub)
- [ ] Container laufen als non-root
- [ ] Read-only Root-Filesystem für Container
- [ ] Resource Limits (CPU/Memory) auf allen Pods
- [ ] Pod Security Standards: restricted
- [ ] Image-Scanning (Trivy/Snyk) in CI/CD
- [ ] Regelmäßige Dependency-Updates (Dependabot)

#### Datenklassifizierung
- [ ] Repo-Allowlist gepflegt und reviewed (quartalsweise)
- [ ] CONFIDENTIAL/RESTRICTED Repos nicht im MCP-Toolset
- [ ] Entwickler-Schulung: Was darf in Prompts, was nicht
- [ ] DLP-Integration falls vorhanden (optional)

---

### Tests (Mindest-Testabdeckung)

```
tests/
├── test_health.py              # Health-Endpoint antwortet
├── test_auth.py                # Ungültiger Key → 401, abgelaufener Key → 401
├── test_anthropic_format.py    # Anthropic Messages Request → korrekter Response
├── test_openai_format.py       # OpenAI Chat Completions → korrekter Response
├── test_model_routing.py       # claude-sonnet → github/anthropic/claude-4-sonnet
├── test_pii_redaction.py       # Email/SSN/IBAN in Prompt → maskiert
├── test_secret_detection.py    # ghp_xxx in Prompt → geblockt
├── test_rate_limiting.py       # N+1 Requests → 429
├── test_budget_limit.py        # Über-Budget → 429 mit Budget-Exceeded
├── test_streaming.py           # SSE-Stream korrekt übersetzt
├── test_tool_use.py            # Tool-Use Requests korrekt übersetzt
└── test_network_policy.py      # Egress nur zu erlaubten Hosts
```

**Test-Tooling:** `pytest` + `httpx` (async) + `respx` (Mocking)

```bash
# Lokal
docker compose up -d
pytest tests/ -v --tb=short

# CI (GitHub Actions)
# → In separatem Workflow, nutzt docker-compose
```

---

### Quick-Start für Entwickler (nach Deployment)

```bash
# 1. Team-Key vom Admin erhalten (z.B. sk-team-backend-xxx)

# 2. Shell-Profil konfigurieren (~/.bashrc oder ~/.zshrc)
export ANTHROPIC_BASE_URL="https://ai-gateway.internal:4000"
export ANTHROPIC_AUTH_TOKEN="sk-team-backend-xxx"
export GITHUB_MCP_PAT="github_pat_xxx"  # Eigener PAT für MCP Repo-Zugriff

# 3. Claude Code starten
claude

# 4. MCP-Server wird automatisch aus .mcp.json geladen (falls im Projekt-Root)
# Oder manuell:
claude mcp add github -e GITHUB_PERSONAL_ACCESS_TOKEN=$GITHUB_MCP_PAT -- \
  docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN ghcr.io/github/github-mcp-server

# 5. Testen
# Claude Code nutzt jetzt GitHub Models (Billing über GitHub)
# UND hat Zugriff auf GitHub-Repos via MCP
```
