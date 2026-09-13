# SignAI — Sign Alphabet Recognition and Learning

A Flask application combining browser webcam capture, sign-alphabet inference, PostgreSQL accounts/history, and learning pages. Model classes cover 26 Latin letters. This is an alphabet-recognition prototype, not a validated continuous sign-language translator.

## How it works

Browser frame → `/api/predict` → preprocessing → TensorFlow model → smoothed prediction → learning interface/history.

The engine supports 63-feature MediaPipe landmark vectors and RGB CNN inputs. It detects model input shape and falls back to demo mode when loading fails. Check model status rather than assuming displayed predictions came from trained weights.

## Source map

| Path | Responsibility |
| --- | --- |
| `app.py` | Routes, authentication, camera/API coordination |
| `cnn_model.py` | Model loading, inference, temporal smoothing |
| `preprocess.py` | Image utilities |
| `config.py` | Environment-based configuration |
| `db_manager.py` | PostgreSQL access and startup schema creation |
| `templates/`, `static/` | Pages, styles, browser logic |
| `models/` | Weights and experiment metadata |
| `training/` | Training scripts/notebook |
| `Dockerfile` | Python 3.11 container entry point |

## Local development

Use Python 3.11, matching the Dockerfile. PostgreSQL is required for working accounts and persistence.

```bash
git clone https://github.com/iimaha-AI/signai13.git
cd signai13
python -m venv .venv
```

Activate with `source .venv/bin/activate` or `.venv\Scripts\Activate.ps1`, then install `python -m pip install -r requirements.txt`.

Review the local `.env`, use `.env.example` as a template, and set your own `DATABASE_URL` and unique `SECRET_KEY`. A development `.env` is currently tracked: `.gitignore` does not untrack existing files. Configuration uses `load_dotenv(override=True)`, so this file can override shell variables. Untracking it and adjusting precedence are pending runtime configuration changes.

```bash
python app.py
```

Use the configured `PORT` (code default: 5000). Database initialization happens on import: select a development database. Camera permission is required. Cloud inference uses browser uploads; server-camera endpoints require physical camera hardware.

## Container

```bash
docker build -t signai .
docker run --rm -p 7860:7860 --env-file .env signai
```

Use a container-specific environment with `FLASK_ENV=production`, a stable secret, and reachable PostgreSQL. For localhost HTTP, configure local cookie settings; use HTTPS/secure cookies for hosting. See [existing deployment guide](README_DEPLOY.md); its provider pricing/account instructions were not verified in this review.

## Model evidence

Values below are recorded metadata, not independently reproduced benchmarks:

| Metadata file | Recorded result |
| --- | --- |
| `landmark_model_meta.json` | Validation accuracy 99.66% |
| `mobilenet_model_meta.json` | Validation accuracy 99.9% |
| `custom_cnn_meta.json` | Test accuracy 5.15% |
| `model_meta.json` | Active-model accuracy is null |

Do not assign the best experiment score to active weights without matching hashes, data split, and preprocessing. Add signer-independent testing, confusion matrices, latency, and live-camera evaluation. Static images do not establish motion-dependent sign recognition.

## Training and limitations

`training/train_real_landmarks.py` expects an ASL image dataset under `dataset/asl_alphabet_train/`. It writes model/metadata files used by the app; train in a separate experimental copy. Raw training data is absent.

In-memory prediction state is combined with a two-worker Docker command; verify cross-worker behavior. Some fallback leaderboard entries are generated demo data. Camera, database, TensorFlow inference, and deployment testing remain outstanding. See [review notes](docs/REVIEW.md).

## Attribution

Document dataset terms, contributor roles, model provenance, and the intended code license. No license is inferred from hosting instructions.

## Known configuration mismatches

`database/schema.sql` is a legacy MySQL reference; PostgreSQL initialization is implemented in `db_manager.py`. The admin training route references missing `fast_train.py` and is not a working training entry point in this snapshot.
