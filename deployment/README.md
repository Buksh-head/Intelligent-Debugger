# Deployment

Use this folder for instructions and files needed to run, deploy, or demonstrate the prototype.

This folder should help another person set up and run the project without relying only on verbal explanation from the team.

## What to Include

- local setup instructions
- deployment instructions
- required software versions
- required accounts or services
- environment variable instructions
- test accounts, if appropriate
- demo instructions
- known deployment limitations

## Minimum Expected Content

By the final submission, this folder should explain:

1. how to install required dependencies
2. how to configure the project
3. how to run the prototype locally
4. how to run tests, where relevant
5. how to access the deployed version, if there is one
6. any known limitations or setup issues

## Important

Do not commit passwords, API keys, access tokens, private keys, or real production configuration files.

If environment variables are needed, provide an example file such as:

```text
.env.example
```

## Local Setup (current scaffold)

**Requirements**: Docker Desktop (includes Docker Compose), and access to the team's shared Supabase project (ask a teammate for an invite if you don't have one). The database schema is already applied to the shared instance. You do **not** need to run any SQL yourself to get started.

**Windows note**: install Docker Desktop with the **WSL2 backend** (default on a recent install) and run these commands from either PowerShell or a WSL2/Git Bash shell, not `cmd.exe`. If your shell doesn't have `cp` or `curl` (plain `cmd.exe`), use Git Bash (installed alongside Git for Windows) instead; the commands below assume a Unix-style shell (Git Bash, WSL2, or macOS/Linux Terminal). If you only have PowerShell, replace `cp` with `Copy-Item` and see the PowerShell alternative for step 4.

1. Copy `.env.example` to `.env` in this folder:

   ```bash
   cp .env.example .env
   ```

   PowerShell: `Copy-Item .env.example .env`

2. Get the real database password: Supabase dashboard → the project (ref `wqfpnncfzhgkidgbpngd`) → **Project Settings → Database**, and fill it into `DATABASE_URL` in your `.env`. Keep the shared pooler host from `.env.example` (`aws-0-ap-southeast-2.pooler.supabase.com:6543`); only replace the password. Fill in any other real values (e.g. `HF_TOKEN`). Never commit `.env`.
3. From this `deployment/` folder, run:

   ```bash
   docker compose up --build
   ```

4. This starts three long-running containers and one setup job:
   - **`backend`** : FastAPI on `http://localhost:8000` (`/health` should return `{"status": "ok"}`), connected to the shared Supabase Postgres via `DATABASE_URL`
   - **`frontend`** : React/Vite on `http://localhost:5173`
   - **`piston`** : the code-execution sandbox on `http://localhost:2000`
   - **`piston-setup`** : a one-shot job that prepares the sandbox's Python runtime, then exits (see step 5)

5. **Sandbox runtime (automatic)**: Piston starts with no language runtimes installed, so `piston-setup` runs `deployment/piston/setup_runtime.py` on every `docker compose up`. There is no manual install step. It:
   1. installs the Python 3.12.0 runtime through the Piston API if it is missing,
   2. `pip install`s the modules in `deployment/piston/requirements.txt` into that runtime,
   3. limits numpy's maths library to one thread (otherwise `import numpy` alone uses most of the sandbox's 3 second CPU limit),
   4. runs a smoke check through the Piston execution API that imports the modules and saves a plot.

   The `backend` container waits for this job to finish successfully. On a fresh `piston-packages` volume the first run downloads the runtime and modules (needs internet access, typically one to a few minutes); later runs take a few seconds because everything persists in that volume. If the job fails, the backend does not start; read the reason with `docker compose logs piston-setup`.

   **Supported Python modules in the sandbox**

   | Module | Source |
   | --- | --- |
   | `numpy` (1.26.x) | bundled with the Piston Python 3.12.0 runtime, pinned below 2 in `requirements.txt` |
   | `pandas`, `scipy` | bundled with the Piston Python 3.12.0 runtime |
   | `matplotlib` | installed from `requirements.txt` |

   The sandbox has no display, so matplotlib uses its non-interactive `Agg` backend: `plt.savefig(...)` works and `plt.show()` does nothing.

   **Adding a module**: add it to `deployment/piston/requirements.txt`, add its import to `SMOKE_CHECK_SOURCE` in `deployment/piston/setup_runtime.py`, then run `docker compose up piston-setup`.

   **Re-running the check by hand**: `docker compose up piston-setup` (exit code 0 means the modules run inside the sandbox). With the stack up, `pytest tests/integration` runs the same check from the host.

6. Verify everything's up: `docker compose ps` should show `backend`, `frontend` and `piston` as `Up` (`piston-setup` has exited by then; `docker compose ps -a` shows it as `Exited (0)`).

### First time setting up the database (only if you're bootstrapping a new/empty Supabase project)

Skip this if you're joining the existing team project: the shared schema is already applied. Only do this if you're standing up a fresh Supabase project from scratch: in the Supabase dashboard, open **SQL Editor** and run the contents of `src/database/schema/schema.sql`, then `src/database/seed-data/seed.sql` if you want sample rows.

### Instructor login one-time setup (Supabase Auth)

Only needs to be done once for the shared Supabase project (like the schema step above).

1. In the Supabase dashboard, go to **Authentication -> Providers** and confirm **Email** is enabled (on by default).
2. Go to **Project Settings -> API** and copy the **anon public** key into `VITE_SUPABASE_ANON_KEY` in your `.env`. `SUPABASE_URL` is the same project URL you already have (no extra dashboard lookup); the backend uses it to fetch Supabase's public JWKS and verify instructor JWTs (signed with ES256), so there's no shared secret to copy or protect.
3. Restrict who can register as an instructor to an allowed email domain, enforced server-side (not just in the UI). In the Supabase dashboard's **SQL Editor**, run:

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

   Then, in **Authentication -> Hooks**, configure this function as the **Before User Created** hook. (Supabase's dashboard for Auth Hooks has changed shape before, if the exact menu name differs from "Before User Created", look for whichever hook fires on new user sign-up in your project's current dashboard.)

## Troubleshooting

- **Backend returns 500 with `failed to resolve host 'db.wqfpnncfzhgkidgbpngd.supabase.co'`**: your `.env` still uses Supabase's direct database host, which is IPv6 only and usually unreachable from Docker. Copy the `DATABASE_URL` format from `.env.example` (the shared pooler host on port 6543) and put your password into it.
- **Backend can't connect to the database**: double check `DATABASE_URL` in your `.env` has the real password (not the `[YOUR-DB-PASSWORD]` placeholder) and that the Supabase project is active (free-tier projects can pause after a week of inactivity; the dashboard will show a "Restore" button if so).
- **Frontend container fails with `main.tsx` missing / not found**: this was a real bug: `deployment/docker-compose.yml` used to build the frontend from `src/frontend`, which is a stale early scaffold with no `main.tsx`. The actual app lives in `src/frontend/src/debugging-assistant-ui/`, and the compose file now points there. If you still hit this, you're likely on an older checkout, so `git pull` and rebuild with `docker compose build --no-cache frontend`. You should not need to delete the container and fall back to running `npm run dev` manually anymore.
- **Manual/non-Docker frontend run** (e.g. Docker is slow or unavailable): `cd` into `src/frontend/src/debugging-assistant-ui` (not `src/frontend`, which is the stale scaffold and has no `main.tsx`), then `npm install` and `npm run dev`. Requires Node 20+ locally. On Windows, if `npm run dev` says `'vite' is not recognized`, it almost always means `npm install` didn't complete in that folder (or was run in the wrong folder); re-run `npm install` there and confirm `node_modules/.bin/vite` exists before trying `npm run dev` again.
- **Frontend fails with `Failed to resolve import "<package>"` after pulling new frontend dependencies**: Docker Compose reuses the frontend's anonymous `node_modules` volume across container recreation by default, so `docker compose up --build` alone can leave a stale, pre-existing container running old dependencies even after the image is rebuilt. Force a fresh volume with `docker compose up -d --build --force-recreate -V frontend` (the `-V` flag renews anonymous volumes) whenever `package.json` changes.
- **Piston install/execute calls fail**: confirm the container is up (`docker logs piston_api`, look for `API server started on 0.0.0.0:2000`) and that the setup job succeeded (`docker compose logs piston-setup`, look for `Piston smoke check passed`).
- **`piston-setup` fails with `Time limit exceeded` in its smoke check**: Piston was already running jobs before the setup changed its runtime settings, and it only reads them on a runtime's first job. Run `docker compose restart piston`, then `docker compose up` again.
- **Student code fails with `ModuleNotFoundError`**: the module is not in the supported list above. Add it as described in step 5.

## Known Limitations

- The sandbox service (Piston) is running and reachable, but `src/backend/app/services/sandbox.py` doesn't call it yet: `run_in_sandbox()` is still a stub (issue #13, in progress).
- The staged hint generator (issues #9, #11) is not wired in: `/api/submit` only returns static analysis findings.
- No deployed/hosted version exists yet.