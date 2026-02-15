# ClaudeX mit GitHub Copilot Business - Deutsche Anleitung

## Zusammenfassung

ClaudeX ist ein LLM-Gateway, das Anfragen von der Claude CLI durch einen zentralen Proxy leitet. Ursprünglich war es für GitHub Models API konfiguriert, aber **Claude-Modelle (Sonnet und Opus) sind NICHT über GitHub Models API verfügbar**.

**Die Lösung:** Claude-Modelle sind jetzt direkt über die Anthropic API integriert und können mit:
1. **Anthropic API Key** (empfohlen für Produktion)
2. **GitHub Copilot Business Subscription** (siehe unten)

## Warum waren Claude-Modelle nicht verfügbar?

Das Problem lag in der Konfiguration:
- ClaudeX war nur für GitHub Models API (`models.github.ai`) konfiguriert
- GitHub Models API bietet OpenAI, Meta, DeepSeek, Mistral, xAI - aber **keine** Anthropic/Claude Modelle
- GitHub Copilot (in der IDE) unterstützt Claude-Modelle, aber das ist ein anderer Dienst
- Die Konfiguration hatte Claude-Modelle auskommentiert mit dem Hinweis "nicht verfügbar"

## Was wurde geändert?

### 1. `config/litellm-config.yaml`
Claude-Modelle hinzugefügt:
- `claude-sonnet-4.5` - Schnell, intelligent, ausgewogen (200K Token)
- `claude-opus-4.6` - Leistungsstark, 1M Token Kontext
- `claude-haiku-4.5` - Schnell und kostengünstig (200K Token)
- Aliases: `claude-sonnet`, `claude-opus`

### 2. `.env.example`
Neue Umgebungsvariable hinzugefügt:
```bash
ANTHROPIC_API_KEY=sk-ant-REPLACE_ME
```

### 3. `README.md`
- Claude-Modell-Tabelle hinzugefügt
- Authentifizierungsoptionen dokumentiert
- Verwendungsbeispiele hinzugefügt

## Verwendung

### Option 1: Mit Anthropic API Key (Empfohlen)

1. **API Key erstellen:**
   - Gehe zu https://console.anthropic.com/settings/keys
   - Erstelle einen neuen API Key
   - Kopiere den Key (beginnt mit `sk-ant-`)

2. **In `.env` einfügen:**
   ```bash
   cp .env.example .env
   # Bearbeite .env und füge deinen Key ein:
   ANTHROPIC_API_KEY=sk-ant-dein-key-hier
   ```

3. **Starten:**
   ```bash
   make restart
   ```

4. **Claude CLI konfigurieren:**
   ```bash
   export ANTHROPIC_BASE_URL=http://localhost:4000
   export ANTHROPIC_AUTH_TOKEN=<dein-litellm-master-key>
   claude
   ```

### Option 2: Mit GitHub Copilot Business

Wenn du bereits GitHub Copilot Business hast und keine separate Anthropic-Rechnung möchtest:

#### 2a. Claude Code CLI direkt nutzen (Einfachste Methode)

```bash
# Installieren
npm install -g @anthropics/claude-code-cli

# Mit GitHub Copilot authentifizieren
claude-code auth github-copilot

# Verwenden (umgeht ClaudeX Gateway)
claude-code
```

**Vorteil:** Keine zusätzlichen Kosten, nutzt deine Copilot-Lizenz
**Nachteil:** Umgeht ClaudeX (keine PII-Maskierung, keine Team-Budget-Kontrolle)

#### 2b. GitHub Copilot durch ClaudeX proxyen (Fortgeschritten)

Für zentrale Kontrolle und PII-Maskierung:

1. **GitHub Copilot Token holen:**
   ```bash
   # In VS Code mit Copilot aktiviert:
   # Command Palette öffnen (Cmd/Ctrl+Shift+P)
   # Befehl: "GitHub Copilot: Show API Token"
   # Token kopieren
   ```

2. **In `.env` einfügen:**
   ```bash
   ANTHROPIC_API_KEY=<dein-github-copilot-token>
   ```

3. **Starten und verwenden:**
   ```bash
   make restart
   export ANTHROPIC_BASE_URL=http://localhost:4000
   export ANTHROPIC_AUTH_TOKEN=<dein-litellm-master-key>
   claude
   ```

**Achtung:** Copilot-Tokens laufen ab und müssen erneuert werden!

## Verfügbare Claude-Modelle

| Modell-Alias | Beschreibung | Kontext |
|--------------|--------------|---------|
| `claude-sonnet-4.5` | Ausgewogen: Schnell + intelligent | 200K |
| `claude-opus-4.6` | Leistungsstark, beste Qualität | 1M |
| `claude-haiku-4.5` | Schnellste, kostengünstig | 200K |
| `claude-sonnet` | Alias für Sonnet 4.5 | 200K |
| `claude-opus` | Alias für Opus 4.6 | 1M |

## Beispiel: Claude über ClaudeX verwenden

```bash
# Mit Anthropic Messages API Format
curl -X POST http://localhost:4000/v1/messages \
  -H "Authorization: Bearer $ANTHROPIC_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-sonnet-4.5",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "Hallo! Erkläre mir Dependency Injection auf Deutsch."}
    ]
  }'
```

## Warum ClaudeX verwenden?

Auch wenn du Claude direkt nutzen könntest, bietet ClaudeX:

### 1. **PII-Maskierung**
Presidio scannt automatisch nach:
- Kreditkartennummern
- E-Mail-Adressen
- Telefonnummern
- GitHub Personal Access Tokens
- API Keys

### 2. **Budget-Kontrolle**
```bash
# Team-Keys mit Limits erstellen
make keys
# Oder manuell:
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d '{
    "team_id": "team-backend",
    "max_budget": 100.0,
    "budget_duration": "30d",
    "models": ["claude-sonnet-4.5", "gpt-4.1-mini"]
  }'
```

### 3. **Audit-Logging**
Alle Anfragen werden in PostgreSQL protokolliert:
- Wer hat welches Modell verwendet?
- Wie viele Tokens wurden verbraucht?
- Wie viel hat es gekostet?

### 4. **Multi-Modell-Zugang**
Ein Gateway für alle Modelle:
- Claude (Anthropic API)
- OpenAI, Meta, DeepSeek (GitHub Models API)
- Zukünftige Provider einfach hinzufügen

## Häufige Fehler

### "Invalid API Key"
- **Ursache:** `ANTHROPIC_API_KEY` nicht gesetzt oder falsch
- **Lösung:** Prüfe `.env` Datei, stelle sicher dass der Key mit `sk-ant-` beginnt

### "Model not found: claude-sonnet"
- **Ursache:** LiteLLM wurde nicht neu gestartet nach Konfigurationsänderung
- **Lösung:** `make restart`

### "Authentication failed"
- **Ursache:** `ANTHROPIC_AUTH_TOKEN` ist nicht dein LiteLLM Master Key
- **Lösung:** Nutze den Wert aus `.env` unter `LITELLM_MASTER_KEY`

## Kosten

### Mit Anthropic API Key:
- **Sonnet 4.5:** $3/1M Input, $15/1M Output
- **Opus 4.6:** $5/1M Input, $25/1M Output
- **Haiku 4.5:** $0.25/1M Input, $1.25/1M Output

### Mit GitHub Copilot Business:
- Teil deiner Copilot-Lizenz ($19/Monat pro User)
- Keine zusätzlichen API-Kosten
- Limits können von GitHub gesetzt werden

## Nächste Schritte

1. **Teste die Konfiguration:**
   ```bash
   make test-quick
   ```

2. **Erstelle Team-Keys:**
   ```bash
   make keys
   ```

3. **Überwache die Verwendung:**
   ```bash
   # Logs ansehen
   make logs-litellm

   # Ausgaben prüfen
   curl http://localhost:4000/spend/logs \
     -H "Authorization: Bearer $LITELLM_MASTER_KEY"
   ```

4. **Produktions-Deployment:**
   ```bash
   # Kubernetes
   make k8s-deploy-prod
   ```

## Support

Bei Problemen:
1. Prüfe die Logs: `make logs-litellm`
2. Teste die Health-Endpoints: `curl http://localhost:4000/health/liveliness`
3. Öffne ein Issue auf GitHub

## Zusammenfassung der Änderungen

- ✅ Claude Sonnet 4.5 hinzugefügt (200K Kontext)
- ✅ Claude Opus 4.6 hinzugefügt (1M Kontext)
- ✅ Claude Haiku 4.5 hinzugefügt
- ✅ Authentifizierung mit Anthropic API dokumentiert
- ✅ GitHub Copilot Business Integration dokumentiert
- ✅ Deutsche Anleitung erstellt
- ✅ Umgebungsvariablen aktualisiert

**Das Problem war:** Die Konfiguration versuchte, Claude-Modelle über GitHub Models API zu nutzen, die dort aber nicht verfügbar sind.

**Die Lösung ist:** Direkte Integration mit Anthropic API, mit zwei Authentifizierungsoptionen (Anthropic Key oder GitHub Copilot).
