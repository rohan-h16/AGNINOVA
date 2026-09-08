# AGNINOVA

Extreme Heatwave Early Warning & Human Thermal Stress Platform.

## Architecture

- Frontend: static HTML/CSS/JS hosted on GitHub Pages
- Backend: FastAPI API hosted on Render, Railway, or another Python hosting platform
- Weather source: Tomorrow.io API

## Required tokens

### 1) Tomorrow.io API key

Create an account at https://www.tomorrow.io/

Then go to:
- Dashboard
- API Keys
- Copy your key

Set it in your backend hosting environment as:

```bash
TOMORROW_API_KEY=your_key_here
```

### 2) GitHub token (optional)

For GitHub Pages or automated deployment via Actions:

- GitHub: https://github.com/settings/tokens
- Use a classic or fine-grained PAT if needed for automation

For normal GitHub Pages publishing, you usually do not need a token if you are using the repository UI.

## Local development

### Backend

```bash
cd Backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# or set the variable manually
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### Frontend

Open the static frontend in a browser or serve it locally:

```bash
cd frontend
python -m http.server 8080
```

Then open: http://127.0.0.1:8080

## GitHub Pages deployment

1. Push the frontend files to GitHub
2. In GitHub, go to Settings -> Pages
3. Choose Deploy from branch
4. Select the appropriate branch and folder
5. Save

Your deployed URL will look like:

```text
https://<your-github-username>.github.io/<your-repo-name>/
```

## Backend hosting

Deploy the FastAPI backend to a Python host such as Render or Railway.

Set this environment variable in the host:

```bash
TOMORROW_API_KEY=your_key_here
```

Then update the backend URL in the frontend: 

- [frontend/index.html](frontend/index.html)

Set the value to your live backend URL, for example:

```html
window.__AGNINOVA_BACKEND_URL__ = "https://your-backend-url.onrender.com";
```

## Notes

- Never commit real API keys to GitHub
- Keep `.env` files local only
- Use hosting platform environment variables instead
