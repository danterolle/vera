# Guida alla Configurazione della Ricerca Web in VERA

Questa guida spiega come abilitare e configurare le ricerche web in tempo reale in VERA, come ottenere gratuitamente la chiave API e come verificare il corretto funzionamento delle ricerche online da parte del modello.

---

## 1. Architettura della Ricerca Web in VERA

VERA implementa un sistema di acquisizione evidenze a più livelli per le informazioni online:

1. **Brave Search API (Consigliato per indicizzazione web completa)**:
   - Fornisce accesso diretto all'indice web globale di Brave.
   - Permette di cercare notizie recenti, incidenti cyber attuali, analisi malware e campagne ransomware.
   - Richiede una chiave API (`VERA_WEB_SEARCH_API_KEY`).
2. **Fallback Web integrato (Senza chiave)**:
   - Quando non è configurata alcuna chiave API, VERA utilizza un fallback basato sul motore pubblico DuckDuckGo e sui cataloghi ufficiali MITRE ATT&CK (software, gruppi, tecniche).
   - Consente di estrarre evidenze e snippet anche in assenza di chiavi a pagamento o account esterni.
3. **Lookup autoritativi per vulnerabilità (CVE)**:
   - Con `VERA_LIVE_SOURCES=true`, VERA interroga direttamente e in tempo reale NVD (NIST), CISA KEV, CVE.org, FIRST EPSS e OSV.dev quando rileva identificatori CVE.

---

## 2. Come Recuperare Gratuitamente la Chiave API di Brave Search

Brave offre un piano gratuito (**Free Tier**) che include **2.000 query al mese senza costi**.

### Passaggi:
1. **Registrazione**:
   - Vai sul portale sviluppatori di Brave: [https://brave.com/search/api/](https://brave.com/search/api/)
   - Clicca su **Get Started** o **Sign Up**.
2. **Creazione dell'Account**:
   - Inserisci la tua email e conferma il link di verifica ricevuto via email.
3. **Selezione del Piano**:
   - Nella sezione **Plans** o **Pricing**, seleziona il piano **Free** (chiamato *Data for AI / Web Search Free*).
   - Il piano gratuito include fino a 2.000 chiamate/mese con rate limit di 1 richiesta al secondo.
4. **Generazione della Chiave API**:
   - Accedi alla dashboard delle chiavi: `https://api.search.brave.com/app/keys`
   - Clicca su **Create New Key**.
   - Assegna un nome (es. `VERA-local`) e copia la chiave generata (ha un formato alfanumerico tipo `BSA...`).

---

## 3. Configurazione di VERA con la Chiave Web

Apri il file `.env` presente nella cartella principale del progetto:

```bash
nano .env   # o tramite il tuo editor di testo preferito
```

Verifica e imposta le seguenti variabili:

```dotenv
# Abilita le sorgenti live online (CVE + Web)
VERA_LIVE_SOURCES=true

# Abilita la ricerca web
VERA_WEB_SEARCH_ENABLED=true

# Inserisci qui la chiave Brave Search ottenuta al punto 2
VERA_WEB_SEARCH_API_KEY=BSA_INSERISCI_QUI_LA_TUA_CHIAVE

# Opzionale: per permettere al modello di decidere autonomamente
# se e quando cercare online durante il ciclo di pensiero (ReAct)
VERA_REACT_ENABLED=false
```

> **Nota**: Se modifichi `.env`, riavvia il server VERA per applicare le modifiche:
> ```bash
> systemctl --user restart vera-api.service
> ```
> oppure, se eseguito manualmente:
> ```bash
> uv run --extra knowledge-graph vera serve
> ```

---

## 4. Come Attivare la Ricerca nelle Conversazioni

VERA attiva la ricerca online in tre circostanze:

1. **Richieste esplicite di ricerca online**:
   - *"Cerca su internet le ultime notizie sul ransomware LockBit"*
   - *"Cerca online cosa è successo con il disservizio CrowdStrike"*
   - *"Fai una ricerca web sulle vulnerabilità zero-day più recenti"*
2. **Richieste su novità, incidenti o dati recenti**:
   - Termini come `ultimi`, `novità`, `notizie`, `aggiornamenti`, `recente`, `incidente` o `breach` attivano automaticamente la rotta con strumenti (`CAG_RAG_TOOL`).
3. **Mancanza di copertura locale**:
   - Se una domanda riguarda un tema di cybersecurity non presente nel Knowledge Graph o nel corpus locale, VERA espande automaticamente la query verso la ricerca web per colmare la lacuna.

---

## 5. Come Verificare il Funzionamento

### Tramite l'Interfaccia Chat (`http://127.0.0.1:8000/chat`):
1. Invia una domanda che richiede dati recenti, ad esempio:
   > *"Cerca online le ultime novità sul ransomware LockBit."*
2. Nella risposta, clicca su **Fonti e dettagli della risposta**:
   - Vedrai le fonti con l'etichetta `Recuperata online` o `web`.
   - Sarà visibile l'URL della pagina consultata (es. CISA, BleepingComputer, MITRE).
   - Sarà elencata la chiamata `HTTP GET` con codice `200`.

### Tramite Chiamata API:
```bash
curl -fsS http://127.0.0.1:8000/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"query":"Cerca su internet informazioni sul ransomware LockBit","origin":"chat"}'
```

Nel payload JSON di ritorno:
- `route` sarà `CAG_RAG_TOOL`.
- `metadata.resource_plan.use_tools` sarà `true`.
- In `evidence` saranno presenti elementi con `source: "web"`, `status: "available"` e `provenance: "live_api"`.
