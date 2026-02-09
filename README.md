# AI Stock Recommender

A multi-agent AI system for stock analysis and portfolio recommendations. The platform uses Google's Agent Development Kit (ADK) with the A2A (Agent-to-Agent) protocol, where a Host Agent orchestrates specialized sub-agents to provide stock analysis, portfolio report analysis, and investment recommendations.

## Components

| Component | Tech Stack | Port | Purpose |
|---|---|---|---|
| **Frontend** | React 19, TypeScript, Tailwind CSS, Firebase Auth | 3000 | User interface with chat, auth, profile, and portfolio views |
| **Host Agent** | FastAPI, Google ADK, A2A SDK, SQLAlchemy | 10001 | Orchestrates agents, serves REST API, manages sessions |
| **Stock Analyser Agent** | Google ADK, A2A SDK, yfinance, Perplexity AI | 10002 | Analyzes stocks, fetches market data, generates recommendations |
| **Stock Report Analyser Agent** | Google ADK, A2A SDK, PyMuPDF | 10003 | Analyzes uploaded portfolio PDFs and financial documents |
| **MCP Server** | FastMCP, yfinance, pandas_ta | stdio | Provides stock data tools (prices, news, technicals) to agents |
| **PostgreSQL** | PostgreSQL 15 | 5432 | Users, sessions, messages, recommendations |
| **Redis** | Redis | 6379 | Async task tracking for long-running agent operations |

## Prerequisites

- **Python** >= 3.12
- **Node.js** >= 18
- **Docker & Docker Compose** (for PostgreSQL)
- **Redis** (local install or Docker)
- **Google API Key** (Gemini API for ADK agents)
- **Firebase Project** (for authentication)

---

## 1. Database Setup

Start PostgreSQL via Docker Compose:

```bash
cd backend
docker-compose up -d
```

This starts a PostgreSQL 15 instance with:
- **Database:** `finance_a2a`
- **User:** `postgres`
- **Password:** `password`
- **Port:** `5432`

The `init.sql` script runs automatically and creates: `users`, `conversation_sessions`, `conversation_messages`, and `agent_states` tables.

### Apply Migrations (if needed)

```bash
cd backend/host_agent
python apply_migration.py
```

---

## 2. MCP Server Setup

The MCP Server provides stock market data tools to the agents via the [Model Context Protocol](https://modelcontextprotocol.io/). It runs as a **stdio subprocess** spawned by the Host Agent and Stock Analyser Agent -- it does not need to be started separately.

### Environment Variables

```bash
cd mcp
cp .env.example .env
```

| Variable | Description |
|---|---|
| `FINNHUB_API_KEY` | Finnhub API key (optional, currently unused -- data comes via yfinance) |
| `ANTHROPIC_API_KEY` | Only needed if running the standalone MCP client test |

### MCP Tools Exposed

| Tool | Description |
|---|---|
| `get_stock_symbol_lookup(query)` | Searches for best-matching stock ticker symbol |
| `get_stock_news(symbol)` | Fetches recent news articles for a stock |
| `get_price_history(symbol, period, interval)` | Historical prices with RSI, MACD, Bollinger Bands |
| `search(query, search_type)` | Yahoo Finance search for quotes or news |
| `get_stock_info(symbol)` | Comprehensive stock info (valuations, financials, balance sheet) |
| `get_stock_recommendations(symbol)` | Analyst recommendations for a stock |
| `get_US_market_news()` | Latest US market news summary |

### MCP Prompts

| Prompt | Description |
|---|---|
| `stock_analysis` | Full stock analysis workflow (symbol lookup, info, technicals, recommendation) |
| `market_overview` | Comprehensive market overview |

### How Agents Call MCP

Both the **Host Agent** and **Stock Analyser Agent** spawn the MCP server as a subprocess using Google ADK's `MCPToolset` with `StdioConnectionParams`:

```python
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams
from mcp import StdioServerParameters

connection_params = StdioConnectionParams(
    server_params=StdioServerParameters(
        command=sys.executable,          # current Python interpreter
        args=["/path/to/mcp/server.py"], # path to MCP server script
        env=mcp_env,
    )
)
stock_mcp_tool = MCPToolset(connection_params=connection_params)
```

The `MCP_DIRECTORY` config variable (in Host Agent and Stock Analyser Agent) points to the `mcp/` folder. The Host Agent uses MCP tools directly for portfolio performance price lookups, while the Stock Analyser Agent uses them within its ADK agent for comprehensive stock analysis.

---

## 3. Backend Setup

### 3a. Host Agent (port 10001)

The central FastAPI server that the frontend talks to. It orchestrates the other agents via the A2A protocol.

```bash
cd backend/host_agent

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r ../requirements.txt
pip install google-adk a2a-sdk python-dotenv uvicorn firebase-admin \
            sqlalchemy psycopg2-binary redis slowapi httpx nest_asyncio \
            boto3 PyMuPDF requests

# Configure environment
cp env.example .env
# Edit .env with your values (see table below)

# Run
python __main__.py
```

#### Host Agent Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | Yes | -- | Google Gemini API key |
| `DATABASE_URL` | Yes | `postgresql://postgres:password@localhost:5432/finance_a2a` | PostgreSQL connection string |
| `FIREBASE_PROJECT_ID` | Yes | -- | Firebase project ID for auth verification |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | Yes | -- | Path to Firebase service account JSON |
| `HOST_AGENT_PORT` | No | `10001` | Port for the Host Agent API |
| `STOCK_ANALYSER_AGENT_URL` | No | `http://localhost:10002` | Stock Analyser Agent URL |
| `STOCK_REPORT_ANALYSER_AGENT_URL` | No | `http://localhost:10003` | Stock Report Analyser Agent URL |
| `MCP_DIRECTORY` | No | (local path) | Path to the `mcp/` directory |
| `REDIS_URL` | No | `redis://localhost:6379` | Redis URL for async task tracking |
| `ENVIRONMENT` | No | `local` | `local` or `production` |

#### Key API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/login` | Firebase ID token login, returns/creates user |
| `POST` | `/api/chats/init` | Initialize a new chat session |
| `POST` | `/api/chats` | Send a message and get a response |
| `POST` | `/api/chats/stream` | Send a message with streaming response |
| `POST` | `/api/chats/async` | Submit a message for async processing |
| `GET` | `/api/chats/tasks/{task_id}` | Poll async task status |
| `GET` | `/api/profile` | Get current user profile |
| `PUT` | `/api/users/{user_id}/profile` | Update user profile |
| `GET` | `/api/users/{user_id}/statistics` | Get user usage statistics |
| `GET` | `/api/sessions/{session_id}/messages` | Get chat history for a session |
| `GET` | `/api/portfolio-performance/{session_id}` | Get portfolio performance data |
| `GET` | `/api/latest-portfolio-performance/{user_id}` | Latest portfolio performance for a user |
| `GET` | `/api/user-recommendations/{user_id}` | Get all stock recommendations for a user |
| `GET` | `/agents/status` | Check status of connected remote agents |
| `GET` | `/health` | Health check |

---

### 3b. Stock Analyser Agent (port 10002)

Runs as a standalone A2A-compatible agent that performs stock analysis using Google ADK + MCP tools.

```bash
cd backend/stockanalyser_agent

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies (uses pyproject.toml)
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your GOOGLE_API_KEY and PERPLEXITY_API_KEY

# Run
python __main__.py
```

#### Stock Analyser Agent Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Yes | Google Gemini API key |
| `PERPLEXITY_API_KEY` | Yes | Perplexity AI API key for research queries |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | Set to `TRUE` to use Vertex AI instead of API key |

The agent starts on **port 10002** and exposes the A2A protocol endpoint. It registers with the skill `stock_analyse` -- "Do a detailed analysis of a stock ticker. Give recommendations for buying or selling."

---

### 3c. Stock Report Analyser Agent (port 10003)

Handles uploaded PDF portfolio statements and financial documents.

```bash
cd backend/stockreport_analyser_agent

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies (uses pyproject.toml)
pip install -e .

# Configure environment (uses same Google API key)
# Create a .env file with GOOGLE_API_KEY

# Run
python __main__.py
```

The agent starts on **port 10003** with the skill `stock_report_analyse` -- "Analyze stock reports, earnings statements, quarterly reports, and other financial documents."

---

## 4. Frontend Setup

The frontend is a React + TypeScript app with Firebase Authentication and Tailwind CSS.

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp env.example .env
# Edit .env with your Firebase config and API URL

# Run development server
npm start
```

The app starts on **http://localhost:3000**.

#### Frontend Environment Variables

| Variable | Required | Description |
|---|---|---|
| `REACT_APP_API_BASE_URL` | Yes | Host Agent API URL (default: `http://localhost:10001/api`) |
| `REACT_APP_FIREBASE_API_KEY` | Yes | Firebase Web API key |
| `REACT_APP_FIREBASE_AUTH_DOMAIN` | Yes | Firebase auth domain |
| `REACT_APP_FIREBASE_PROJECT_ID` | Yes | Firebase project ID |
| `REACT_APP_FIREBASE_STORAGE_BUCKET` | Yes | Firebase storage bucket |
| `REACT_APP_FIREBASE_MESSAGING_SENDER_ID` | Yes | Firebase messaging sender ID |
| `REACT_APP_FIREBASE_APP_ID` | Yes | Firebase app ID |

### Firebase Setup

1. Create a Firebase project at [Firebase Console](https://console.firebase.google.com/)
2. Enable **Email/Password** and **Google** sign-in providers under Authentication
3. Get the web app config and fill in the frontend `.env`
4. Download a service account JSON key and set `FIREBASE_SERVICE_ACCOUNT_PATH` in the Host Agent `.env`

---

## 5. Start Everything (Local Development)

Start services in this order:

```bash
# Terminal 1 - Database
cd backend && docker-compose up -d

# Terminal 2 - Redis (if not using Docker)
redis-server

# Terminal 3 - Stock Analyser Agent
cd backend/stockanalyser_agent && source .venv/bin/activate && python __main__.py

# Terminal 4 - Stock Report Analyser Agent
cd backend/stockreport_analyser_agent && source .venv/bin/activate && python __main__.py

# Terminal 5 - Host Agent (start after remote agents are up)
cd backend/host_agent && source .venv/bin/activate && python __main__.py

# Terminal 6 - Frontend
cd frontend && npm start
```

### Verify

- Frontend: http://localhost:3000
- Host Agent API: http://localhost:10001/health
- Stock Analyser Agent: http://localhost:10002/health
- Agent connectivity: http://localhost:10001/agents/status

---

## Agent Communication Flow

1. Frontend sends a chat message with Firebase auth token to Host Agent (`POST /api/chats`)
2. Host Agent validates the token, manages the session in PostgreSQL
3. Based on user intent, Host Agent delegates to the appropriate sub-agent via the A2A protocol
4. Sub-agents use MCP tools (stock data via yfinance) and Google Gemini (LLM reasoning) to generate analysis
5. Results flow back through A2A to Host Agent, which persists them to the database and returns the response to the frontend
6. For portfolio performance tracking, Host Agent calls MCP tools directly to fetch current stock prices
