# Fix LLM 500 Error

## Problem

The NVIDIA NIM API is returning 500 Internal Server Error:
```
litellm.InternalServerError: Error code: 500 - Inference connection error
```

This is typically caused by:
1. The model path being incorrect or deprecated
2. NVIDIA API service issues
3. Rate limiting on the API key

## Solution 1: Use a Different NVIDIA Model ✅

The current model `openai/google/gemma-4-31b-it` may not be available. Try these working alternatives:

### Edit `profiler/agent/llm_factory.py` line 10:

**Current:**
```python
DEFAULT_NVIDIA_MODEL = "openai/google/gemma-4-31b-it"
```

**Replace with one of these working models:**

```python
# Option 1: Meta Llama (fast, good quality)
DEFAULT_NVIDIA_MODEL = "meta/llama-3.1-8b-instruct"

# Option 2: Mistral (very fast, efficient)
DEFAULT_NVIDIA_MODEL = "mistralai/mistral-7b-instruct-v0.3"

# Option 3: Mixtral (powerful, slower)
DEFAULT_NVIDIA_MODEL = "mistralai/mixtral-8x7b-instruct-v0.1"

# Option 4: Google Gemma (if available)
DEFAULT_NVIDIA_MODEL = "google/gemma-2b-it"
```

## Solution 2: Switch to OpenAI (Most Reliable) ⭐

OpenAI's API is more stable and reliable.

### 1. Get an OpenAI API Key
- Go to https://platform.openai.com/api-keys
- Create a new API key

### 2. Update `.env` file:
```bash
OPENAI_API_KEY=sk-proj-your-actual-key-here
OPENAI_MODEL=gpt-4o-mini
```

### 3. Restart the web backend:
```powershell
# Stop the current server (Ctrl+C in the terminal)
# Then restart with OpenAI provider:
.venv\Scripts\activate
python -m uvicorn frontend.web_backend:app --host 127.0.0.1 --port 5500
```

### 4. In the browser, refresh and the chat will now use OpenAI

## Solution 3: Test NVIDIA API Directly

Test if the NVIDIA API is working at all:

```powershell
.venv\Scripts\activate
python -c "
import os
from dotenv import load_dotenv
load_dotenv()

# Test with litellm
import litellm
response = litellm.completion(
    model='meta/llama-3.1-8b-instruct',
    messages=[{'role': 'user', 'content': 'Say hi'}],
    api_base='https://integrate.api.nvidia.com/v1',
    api_key=os.getenv('NVIDIA_API_KEY_1')
)
print(response.choices[0].message.content)
"
```

If this fails, the NVIDIA API itself is down or your key has issues.

## Solution 4: Quick Model Override (No Code Changes)

You can override the model via environment variable without editing code:

```powershell
$env:NVIDIA_MODEL = "meta/llama-3.1-8b-instruct"
python -m uvicorn frontend.web_backend:app --host 127.0.0.1 --port 5500
```

## Recommended Fix (Easiest)

**Change line 10 in `profiler/agent/llm_factory.py` to:**
```python
DEFAULT_NVIDIA_MODEL = "meta/llama-3.1-8b-instruct"
```

Then restart the web backend server (Ctrl+C and run the uvicorn command again).

This model is:
- ✅ Fast (sub-second responses)
- ✅ Reliable on NVIDIA NIM
- ✅ Good quality for tool calling
- ✅ Free tier available

## After the Fix

1. Restart the web backend server
2. Refresh your browser at http://127.0.0.1:5500
3. Try sending a message: "List files in ./data"
4. Should work without 500 errors ✅

## Still Having Issues?

Check the logs:
- Web backend terminal: Look for LiteLLM errors
- MCP server terminal: Should show tool invocations
- Browser DevTools Console: Check for WebSocket messages

Or switch to OpenAI which is more stable for production use.
