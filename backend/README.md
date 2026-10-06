# ATEON One Backend

Unified Python FastAPI backend providing:
- **REST APIs**: Authentication, Attendance, User Management, and Module Endpoints
- **Realtime Socket.IO Server**: Full WebSockets & Polling on `/api/socket` and `/socket.io`
- **WebRTC Signalling**: Realtime Audio/Video peer connections
- **Internal Event Dispatch**: `/api/internal/emit` endpoint for server actions

---

## Setup & Running

1. **Activate virtual environment:**
   - Windows PowerShell:
     ```powershell
     cd backend
     .\venv\Scripts\activate
     ```
   - Linux / macOS:
     ```bash
     cd backend
     source venv/bin/activate
     ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment:**
   Ensure `.env` contains your database connection string and secret key:
   ```env
   DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/ateonlabs"
   SECRET_KEY="dev-secret-key-ateon-one-2024-local"
   INTERNAL_SECRET="dev_secret"
   ```

4. **Seed Database (if needed):**
   ```bash
   python scripts/seed_dev.py
   ```

5. **Start FastAPI Backend Server:**
   ```powershell
   uvicorn app.main:app --reload --port 8000
   ```

> **Note**: The standalone Node.js server (`server.js` on port 3001) has been completely migrated to FastAPI. All REST APIs, realtime Socket.IO connections, and WebRTC signalling now run on FastAPI (port 8000).
