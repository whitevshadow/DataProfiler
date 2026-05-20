# Data Profiler Frontend - Quick Start Guide

## ✅ Current Status

**Both servers are running and fully operational:**

- **Frontend Web Server**: http://127.0.0.1:5500
- **MCP Tool Server**: http://127.0.0.1:8080/sse

## 🚀 Access the UI

Open your browser to: **http://127.0.0.1:5500**

The UI should show **"Connected"** status in the sidebar (green dot).

## 🛠️ Available MCP Tools

The frontend has access to all 8 MCP tools via the chat interface:

### 1. **list_supported_files**
- List supported data files in a directory
- Example: `"List all supported files in the data directory"`

### 2. **profile_file**
- Profile a single file and generate canonical/profile JSON
- Example: `"Profile the file at data/customers.csv"`

### 3. **profile_directory**
- Profile all supported files in a directory
- Example: `"Profile all files in ./data"`

### 4. **enrich_relationships**
- Generate LLM descriptions and detect semantic relationships
- Example: `"Enrich relationships for my profiled tables"`

### 5. **enrich_low_cardinality**
- Enrich low-cardinality columns with semantic intelligence (LCIL)
- Example: `"Enrich low cardinality columns"`

### 6. **get_quality_summary**
- Get data quality metrics from profile JSON
- Example: `"Show quality summary for warehouse_colors"`

### 7. **get_table_relationships**
- Retrieve detected relationships
- Example: `"What relationships exist between my tables?"`

### 8. **generate_erd**
- Generate an interactive ER diagram HTML
- Example: `"Generate an ER diagram"`

## 📡 API Endpoints

The web backend provides these REST/WebSocket endpoints:

### REST APIs
- `GET /api/sessions` - List chat sessions
- `POST /api/sessions` - Create/update session
- `POST /api/upload` - Upload data files (CSV, Parquet, JSON, etc.)
- `GET /api/connections` - List database connections
- `POST /api/connections` - Register new connection
- `POST /api/connections/{id}/test` - Test connection
- `DELETE /api/connections/{id}` - Remove connection

### WebSocket
- `WS /ws/chat` - Real-time chat with LangGraph agent

## 🎨 UI Features

### Quick Actions (shown on empty chat)
- Upload Files
- Profile Directory
- Detect Relationships
- Enrich & Analyze
- ER Visuals
- List Files

### File Upload
- Drag & drop files directly onto the chat area
- Or use the "Upload Files" button
- Supports: CSV, Parquet, JSON, Excel, DuckDB, SQLite, and compressed files
- Two storage modes:
  - **Temporary**: `/data/uploads` (default)
  - **Persistent**: `/data/mounted`

### Live Stats
During pipeline execution, see real-time metrics:
- Tables profiled
- Total rows
- Total columns
- FK candidates discovered
- Elapsed time

### Theme Toggle
Switch between light and dark mode (sidebar)

### Command Palette
Press `Ctrl+K` to open quick actions

## 🔧 How It Works

```
Browser (Port 5500)
    ↓
WebSocket /ws/chat
    ↓
Starlette Backend (web_backend.py)
    ↓
LangGraph Chat Agent (profiler/agent/chatbot.py)
    ↓
MCP Tools via SSE (Port 8080)
    ↓
Profiler Services (profiler/services.py)
```

## 🏃 Running the Servers

### Start Both Servers (2 terminals required)

**Terminal 1 - MCP Server:**
```powershell
cd f:\agentic_profiler\new
.venv\Scripts\activate
python -m profiler --transport sse --port 8080
```

**Terminal 2 - Web Backend:**
```powershell
cd f:\agentic_profiler\new
.venv\Scripts\activate
python -m uvicorn frontend.web_backend:app --host 127.0.0.1 --port 5500
```

### Stop Servers
Press `Ctrl+C` in each terminal

## 📝 Example Workflows

### Basic Profiling
1. Upload CSV files via drag-and-drop
2. Agent automatically profiles them
3. View results in expandable preview cards

### Full Pipeline
```
You: "Profile all files in ./data, then detect relationships and generate an ER diagram"
```

The agent will:
1. Profile all tables
2. Generate LLM descriptions
3. Detect foreign key candidates
4. Generate ER diagram visualization

### Quality Analysis
```
You: "Show me quality issues in warehouse_colors"
```

### Relationship Discovery
```
You: "What relationships exist between sales_orders and sales_customers?"
```

## 🐛 Troubleshooting

### "Disconnected" Status
- Verify both servers are running
- Check ports 5500 and 8080 are not in use by other apps
- Refresh the browser page

### WebSocket Connection Failed
- Ensure MCP server (port 8080) started successfully
- Check for errors in the server terminal output
- Verify NVIDIA_API_KEY is set in .env file

### Tool Execution Errors
- Check MCP server logs in Terminal 1
- Verify the tool has required dependencies (e.g., output/profiles/ exists for enrichment)
- Ensure file paths are correct (relative to project root)

## 📂 Project Structure

```
frontend/
  ├── index.html          # Main UI
  ├── app.js              # Frontend logic (WebSocket, chat, file upload)
  ├── style.css           # Enhanced styling (teal/amber theme)
  ├── web_backend.py      # Starlette backend (NEW)
  └── neuleap_logo.jpg    # Logo

profiler/
  ├── server.py           # MCP tool registration
  ├── services.py         # Tool implementations
  └── agent/
      ├── chatbot.py      # LangGraph chat graph
      ├── llm_factory.py  # LLM configuration
      └── state.py        # Chat state management
```

## 🎯 Next Steps

1. Open http://127.0.0.1:5500 in your browser
2. Verify "Connected" status shows in sidebar
3. Try a quick action: "List all supported files in the data directory"
4. Upload a CSV file via drag-and-drop
5. Ask the agent to profile it

Enjoy your fully connected data profiler! 🚀
