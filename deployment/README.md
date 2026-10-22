# Deployment

How to run Error Guide locally, how the production deployment is set up, and how to fix common problems. The quick version is in the [root README](../README.md#quick-start); this page has the detail.

| File | Purpose |
| --- | --- |
| [`docker-compose.yml`](docker-compose.yml) | Local stack: backend, frontend, Piston sandbox and its setup job |
| [`.env.example`](.env.example) | Template for the environment variables. Copy it to `.env` (git-ignored) |
| [`piston/setup_runtime.py`](piston/setup_runtime.py), [`piston/requirements.txt`](piston/requirements.txt) | Installs the Python runtime and modules into the sandbox and smoke-checks them |

**Contents**

- [Requirements](#requirements)
- [Environment variables](#environment-variables)
- [Run locally with Docker](#run-locally-with-docker)
- [Run locally without Docker](#run-locally-without-docker)
- [Set up a new Supabase project](#set-up-a-new-supabase-project)
- [Production deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)

---

## Requirements

| Tool | Version | Needed for |
| --- | --- | --- |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose) | Any recent version. On Windows, use the WSL2 backend | The local stack |
| Access to the team's Supabase project | Ask a teammate for an invite | The database password and anon key |
| A [Groq](https://console.groq.com) API key | | Hints, answers and instructor insights |
| Python | 3.12 (3.10 or newer works) | Running without Docker, and the tests |
| Node.js | 22 LTS (20.19 or newer works) | Running without Docker, and the tests |

On Windows, run the commands below in Git Bash, WSL2 or PowerShell, not `cmd.exe`. In PowerShell, use `Copy-Item` instead of `cp`.

## Environment variables

All of them live in `deployment/.env`, which both Docker Compose and the Vite dev server read. Start from the template:

```bash
cp deployment/.env.example deployment/.env
```

| Variable | Used by | Value |
| --- | --- | --- |
| `DATABASE_URL` | Backend | Supabase Postgres through the **connection pooler** (`aws-0-ap-southeast-2.pooler.supabase.com:6543`), as in the template. Put the database password from Supabase **Project Settings → Database** in place of `[YOUR-DB-PASSWORD]` |
| `SUPABASE_URL` | Backend | `https://<project-ref>.supabase.co`. The backend fetches Supabase's public keys from it to verify logins; there is no shared secret |
| `GROQ_API_TOKEN` | Backend | Groq API key for hints, answers and reply classification |
| `INSTRUCTOR_TOKEN` | Backend | Groq API key for the instructor dashboard's AI insights; can be the same key |
| `GROQ_API_URL` | Backend | `https://api.groq.com/openai/v1`. Any OpenAI-compatible endpoint works |
| `PISTON_URL` | Backend | `http://piston:2000` inside Docker (the default), `http://localhost:2000` when the backend runs outside Docker, or the production VM's address |
| `PISTON_PYTHON_VERSION` | Backend | Optional, default `3.12.0` |
| `VITE_SUPABASE_URL` | Frontend | Same project URL as `SUPABASE_URL` |
| `VITE_SUPABASE_ANON_KEY` | Frontend | Supabase **Project Settings → API → anon public** key. Safe to expose in the browser by design |
| `VITE_API_URL` | Frontend, production only | The deployed API's address. Leave unset locally, where Vite forwards `/api` to the backend |

Never commit `.env`. It is git-ignored, and production values live in Vercel's environment settings.

## Run locally with Docker

From the repository root:

```bash
cp deployment/.env.example deployment/.env    # then fill in the values above
docker compose -f deployment/docker-compose.yml up --build
```

This starts three long-running containers and one setup job:

| Service | Address | What it is |
| --- | --- | --- |
| `frontend` | <http://localhost:5173> | The web app (Vite dev server, reloads on save) |
| `backend` | <http://localhost:8000> | The API (`/health` returns `{"status":"ok"}`; interactive API docs at `/docs`) |
| `piston` | <http://localhost:2000> | The code execution sandbox |
| `piston-setup` | none | One-shot job that prepares the sandbox, then exits |

Check it is up with `docker compose -f deployment/docker-compose.yml ps`: `backend`, `frontend` and `piston` should be `Up`, and `piston-setup` should show `Exited (0)` with `ps -a`. Stop everything with `docker compose -f deployment/docker-compose.yml down`.

### The sandbox runtime

Piston starts with no language runtimes, so `piston-setup` runs [`setup_runtime.py`](piston/setup_runtime.py) on every `up`. It:

1. installs the Python 3.12.0 runtime through the Piston API if it is missing,
2. `pip install`s the modules in [`piston/requirements.txt`](piston/requirements.txt) into that runtime,
3. limits NumPy's maths library to one thread (otherwise `import numpy` alone uses most of the sandbox's CPU limit),
4. runs a smoke check through the Piston API that imports the modules and saves a plot.

The backend waits for this job to succeed. The first run downloads the runtime and modules (needs internet, one to a few minutes); later runs take seconds because they persist in the `piston-packages` volume. Python's run timeout is raised to 20 seconds (`PISTON_LIMIT_OVERRIDES`) so NumPy and plotting programs are not cut off.

**Modules student code can import**

| Module | Source |
| --- | --- |
| `numpy` (1.26.x) | Bundled with Piston's Python 3.12.0 runtime, pinned below 2 in `requirements.txt` |
| `pandas`, `scipy` | Bundled with the runtime |
| `matplotlib` | Installed from `requirements.txt` |

The sandbox has no display, so Matplotlib uses its non-interactive `Agg` backend: `plt.savefig(...)` works and `plt.show()` does nothing.

**Adding a module:** add it to `piston/requirements.txt`, add its import to `SMOKE_CHECK_SOURCE` in `piston/setup_runtime.py`, then run `docker compose -f deployment/docker-compose.yml up piston-setup`.

## Run locally without Docker

Useful when Docker is slow or unavailable. Piston still needs Docker, so either run just the sandbox in Docker or point `PISTON_URL` at another Piston server.

```bash
# 1. The sandbox only (or skip this and set PISTON_URL to another server)
docker compose -f deployment/docker-compose.yml up -d piston piston-setup

# 2. The backend, in one terminal (set PISTON_URL=http://localhost:2000 in deployment/.env first)
cd src/backend
python3.12 -m venv .venv && source .venv/bin/activate    # Windows (Git Bash): source .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000 --env-file ../../deployment/.env

# 3. The frontend, in another terminal
cd src/frontend
npm ci
npm run dev                  # http://localhost:5173, forwards /api to localhost:8000
```

## Set up a new Supabase project

**Skip this if you are joining the existing team project**: its schema is already applied. Only do this to stand up Error Guide on a fresh Supabase project.

1. Create a project in the [Supabase dashboard](https://supabase.com/dashboard).
2. In the **SQL Editor**, run, in order:
   1. [`src/database/schema/schema.sql`](../src/database/schema/schema.sql): tables, indexes, row level security, the deletion functions and the dashboard's count views.
   2. [`src/database/schema/auth-roles.sql`](../src/database/schema/auth-roles.sql): the `profiles` table and the trigger that records each new account's role.
   3. Optionally, [`src/database/seed-data/seed.sql`](../src/database/seed-data/seed.sql) for sample rows (synthetic, no real student data).
3. Fill in `DATABASE_URL`, `SUPABASE_URL`, `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` from the new project.
4. Follow the instructor login setup below.

### Instructor login one-time setup (Supabase Auth)

Only needs doing once per Supabase project.

1. In **Authentication → Providers**, confirm **Email** is enabled (it is by default).
2. In **Project Settings → API**, copy the **anon public** key into `VITE_SUPABASE_ANON_KEY`.
3. **Check that logins carry the role.** The frontend reads each account's role from `public.profiles` (set up by `auth-roles.sql`), but the backend reads it from `app_metadata.role` inside the login token ([`auth.py`](../src/backend/app/auth.py)) and refuses any logged-in request where it is missing. The SQL that fills in `app_metadata.role` on the team project is not in this repository. On a new project, register a test account, decode its access token and confirm `app_metadata.role` is there; if it is not, copy the role into the user's app metadata (`auth.users.raw_app_meta_data`) when the account is created.
4. Optionally, restrict sign-ups to an email domain, enforced on the server rather than just in the interface. In the **SQL Editor**, run:

   ```sql
   create or replace function public.restrict_instructor_signup_domain(event jsonb)
   returns jsonb
   language plpgsql
   as $$
   declare
     allowed_domain text := 'uq.edu.au'; -- change to the real allowed domain
     user_email text := event->'user'->>'email';
   begin
     if user_email is null or right(user_email, length(allowed_domain) + 1) <> ('@' || allowed_domain) then
       return jsonb_build_object(
         'decision', 'reject',
         'message', format('Only @%s email addresses can register.', allowed_domain)
       );
     end if;
     return jsonb_build_object('decision', 'continue');
   end;
   $$;
   ```

   Then, in **Authentication → Hooks**, set this function as the **Before User Created** hook (if the menu name has changed, use whichever hook runs on new sign-ups). As written, the hook applies to **every** account, so it would also turn away students whose address is `@student.uq.edu.au`; to restrict instructors only, check `event->'user'->'user_metadata'->>'role'` first. See [risk R11](../docs/risks/risks.md#r11-anyone-can-register-as-an-instructor).

## Production deployment

```text
push to main ──► GitHub Action ──► public repo ──► Vercel (web app + API)
                 sync-public.yml   Buksh-head/        │
                                   Intelligent-       ├──► Google Cloud VM (Piston)
                                   Debugger           ├──► Supabase (Postgres + Auth)
                                                      └──► Groq API
```

| Part | Where | How it is configured |
| --- | --- | --- |
| Web app | Vercel, <https://intelligent-debugger.vercel.app> | Built from `src/frontend` (`npm run build`). [`vercel.json`](../src/frontend/vercel.json) sends every path to `index.html` so the app's routes work on refresh. Environment: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL` |
| API | Vercel Python function, Sydney region | Built from `src/backend`. [`vercel.json`](../src/backend/vercel.json) routes every request to `app/main.py`. Environment: every backend variable in the table above, with `PISTON_URL` set to the VM. The deployed requirements leave out SHAP, LIME and DiCE so the function stays under Vercel's 500 MB limit |
| Sandbox | Google Cloud VM running Docker | The same `piston` and `piston-setup` services as `docker-compose.yml`. Piston cannot run on Vercel because it needs a privileged container and a persistent volume |
| Database and accounts | Supabase | The team's shared project |
| Allowed origins | [`src/backend/app/main.py`](../src/backend/app/main.py) | CORS allows `http://localhost:5173` and the production web app only. Add any new frontend address there |

**How a change reaches production.** The course repository is private, so [`.github/workflows/sync-public.yml`](../.github/workflows/sync-public.yml) runs on every push to `main` and copies `src/`, `deployment/` and the root package files to the public repository [Buksh-head/Intelligent-Debugger](https://github.com/Buksh-head/Intelligent-Debugger), which Vercel deploys from. It needs a `PUBLIC_REPO_TOKEN` secret with write access to that repository. `.env` files are git-ignored, so they are never in the checkout and cannot be copied.

### Set up the sandbox VM

The production sandbox runs on a Google Cloud Compute Engine VM, set up by hand in the console.

| Setting | Value |
| --- | --- |
| Name | `piston-api-server` |
| Zone | `us-central1-a` |
| Machine type | `e2-micro` (2 vCPUs, 1 GB memory) |
| Boot disk | Ubuntu 24.04 LTS Minimal (x86/64), 30 GB standard persistent disk, daily snapshot schedule |
| Firewall | HTTP and HTTPS traffic allowed (network tags `http-server`, `https-server`), plus a rule for TCP port 2000 (step 4) |
| External IP | Ephemeral |
| Provisioning | Standard, automatic restart on, migrates on host maintenance |

1. **Create the VM** in **Compute Engine → VM instances → Create instance** with the settings above.
2. **Make sure Docker is installed.** SSH in from the console's **SSH** button and run `docker compose version`. If it is missing, install Docker Engine for Ubuntu ([instructions](https://docs.docker.com/engine/install/ubuntu/)).
3. **Start Piston.** Clone the public repository and start the sandbox:

   ```bash
   git clone https://github.com/Buksh-head/Intelligent-Debugger.git
   cd Intelligent-Debugger
   sudo docker compose -f deployment/docker-compose.yml up -d piston piston-setup
   ```

   `piston` has `restart: unless-stopped`, so it comes back by itself after the VM reboots. Check the setup job finished with `sudo docker compose -f deployment/docker-compose.yml ps -a` (`piston-setup` should show `Exited (0)`).
4. **Open port 2000.** In **VPC network → Firewall**, create an ingress rule allowing TCP `2000` from `0.0.0.0/0` to the VM.
5. **Point the API at it.** Copy the VM's **External IP address** from its details page. In Vercel, open the API project's **Settings → Environment Variables**, set `PISTON_URL` to `http://<external-ip>:2000`, then **redeploy**: Vercel only applies new values to new deployments.
6. **Check it.** `curl http://<external-ip>:2000/api/v2/runtimes` should list Python `3.12.0`, and running code in the web app should work.

**The IP is ephemeral.** It changes whenever the VM is stopped and started (not on a plain reboot), and you then have to repeat step 5. Reserving a static address (**VPC network → IP addresses → Reserve**) avoids that.

**The sandbox is open to the internet.** Vercel functions have no fixed outgoing IP addresses, so the port 2000 rule cannot be narrowed to the API, and anyone who finds the address can run code on the VM. Piston isolates each run, but nothing limits who calls it.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Backend returns 500 with `failed to resolve host 'db.<ref>.supabase.co'` | `DATABASE_URL` uses Supabase's direct host, which is IPv6 only and usually unreachable from Docker. Use the pooler host from `.env.example` |
| Backend cannot connect to the database | Check `DATABASE_URL` has the real password, not `[YOUR-DB-PASSWORD]`, and that the Supabase project is not paused (the dashboard shows a **Restore** button if it is) |
| Every logged-in request returns 403 | The login token has no `app_metadata.role`. See step 3 of the [instructor login setup](#instructor-login-one-time-setup-supabase-auth) |
| Hints say "The hint generator is busy right now" | Groq's rate limit was hit. Wait a minute; check `GROQ_API_TOKEN` is valid |
| Hints say "having trouble generating a hint" | The Groq call failed. Check `GROQ_API_TOKEN` and `GROQ_API_URL`, and the backend logs (`docker compose -f deployment/docker-compose.yml logs backend`) |
| The frontend fails with `Failed to resolve import "<package>"` after pulling | Compose reuses the old `node_modules` volume. Run `docker compose -f deployment/docker-compose.yml up -d --build --force-recreate -V frontend` whenever `package.json` changes |
| `'vite' is not recognized` when running without Docker | `npm ci` did not finish in `src/frontend`. Re-run it there and check `node_modules/.bin/vite` exists |
| The backend never starts | `piston-setup` failed, and the backend waits for it. Read why with `docker compose -f deployment/docker-compose.yml logs piston-setup` |
| `piston-setup` fails with `Time limit exceeded` | Piston ran jobs before the setup changed its limits, and only reads them on a runtime's first job. Run `docker compose -f deployment/docker-compose.yml restart piston`, then `up` again |
| Running code fails, or `docker logs piston_api` has no `API server started` line | Piston is not up. Check `docker compose -f deployment/docker-compose.yml ps` and that `PISTON_URL` matches where it runs |
| Student code fails with `ModuleNotFoundError` | The module is not installed in the sandbox. Add it as described in [The sandbox runtime](#the-sandbox-runtime) |
| The browser console shows a CORS error | The frontend's address is not in `allow_origins` in `src/backend/app/main.py` |

## Known limitations

- **Python only.** Java and JavaScript appear as "coming soon": the sandbox has no runtimes for them yet.
- **Shared database.** Development and production use the same Supabase project, so local test runs appear in the instructor dashboard. A separate project for development would avoid that.
- **Unauthenticated routes.** The run, hint and analytics routes do not check a login yet ([risk R15](../docs/risks/risks.md#r15-the-run-hint-and-analytics-endpoints-do-not-check-a-login)).
- **No scheduled purge.** The database has the function, but no schedule runs it ([risk R12](../docs/risks/risks.md#r12-personal-data-is-kept-longer-than-needed)).
- **Manual sandbox host.** The production Piston VM is set up by hand following [Set up the sandbox VM](#set-up-the-sandbox-vm); no script or infrastructure code creates it.
