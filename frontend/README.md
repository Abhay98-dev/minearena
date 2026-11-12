# MineArena web interface

This React interface connects to the FastAPI privacy gateway in the repository root.

## Run locally

Start the backend from the repository root using the setup in the root `README.md`:

```powershell
uvicorn app.main:app --reload --app-dir backend
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

The UI uses `http://localhost:8000/api/v1` by default. Set `VITE_API_BASE_URL` in a local `.env` file to point it at another API base URL. For an offline demo, select **Mock (offline demo)** in the provider menu.

Use synthetic or approved text only. The frontend displays the API response, while detection, masking, the outbound leakage guard, reinsertion, and auditing run in the backend.
