# SignAI — Cloud Deployment Guide

This version of SignAI has been migrated from **SQLite → PostgreSQL** and is ready for free cloud hosting on **Hugging Face Spaces** (Docker) with a **Neon** PostgreSQL database.

---

## 1. Create the PostgreSQL database on Neon (free)

1. Go to <https://neon.tech> and sign in with GitHub.
2. Click **Create Project** → name it `signai` → region: closest to you → **Create**.
3. On the project dashboard, click **Connectionstring** → copy the value. It looks like:
   ```
   postgresql://signai_owner:xxxxxxxxxx@ep-xxxx-xxxx.region.aws.neon.tech/signai?sslmode=require
   ```
4. Save this string — you'll paste it as `DATABASE_URL` in step 3.

---

## 2. Create the Hugging Face Space

1. Go to <https://huggingface.co/login> and sign in with GitHub.
2. Click your avatar → **New Space**.
3. Configure:
   - **Owner:** your username
   - **Space name:** `signai13`
   - **License:** MIT
   - **SDK:** **Docker** (this is critical — do not pick Gradio/Streamlit)
   - **Visibility:** Public
4. Click **Create Space**.

---

## 3. Add secrets to the Space

In your Space, open the **Settings** tab → scroll to **Variables and secrets** → add these as **Secrets** (not Variables):

| Name | Value |
|------|-------|
| `DATABASE_URL` | the Neon connection string from step 1 |
| `SECRET_KEY` | any long random string (e.g. `openssl rand -hex 32`) |

> Secrets are encrypted and never exposed in the UI.

---

## 4. Push your code to the Space

Hugging Face Spaces are git repos. Add the Space as a remote and push:

```bash
# Replace <USER> with your HF username
git remote add space https://huggingface.co/spaces/<USER>/signai13
git push space main
```

When prompted, authenticate with a **Hugging Face access token** (create one at <https://huggingface.co/settings/tokens> with **Write** permission). Use any string as the username.

---

## 5. Wait for the build, then visit the app

- The Space will show a `Building` status for ~5–10 minutes (TensorFlow is large).
- Once it says `Running`, your app is live at:
  ```
  https://<USER>-signai13.hf.space
  ```

The first request after a cold start may take 10–20 seconds while TensorFlow loads the model.

---

## How the migration was done

| File | Change |
|------|--------|
| `db_manager.py` | Rewritten from `sqlite3` to `psycopg2` (PostgreSQL). All function signatures kept identical. |
| `config.py` | Reads `DATABASE_URL` from env; falls back to `DB_USER` / `DB_HOST` / etc. |
| `requirements.txt` | `PyMySQL` → `psycopg2-binary`; `tensorflow` → `tensorflow-cpu`; `opencv-python` → `opencv-python-headless`; removed `pyttsx3` (no audio drivers on the server). |
| `Dockerfile` | Added — Python 3.11 slim + system deps + gunicorn on port 7860. |
| `.dockerignore` | Added — keeps the image lean. |

The browser-side webcam flow is unchanged: the user captures a frame in the browser and POSTs it as base64 to `/api/predict`. The server-side camera manager (`/api/predict/frame`) is left in place but won't work on the cloud (no physical webcam) — that's expected.
