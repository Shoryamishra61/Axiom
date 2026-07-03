# Axiom

Axiom is a high-performance, fault-tolerant distributed job scheduling and monitoring platform. It uses PostgreSQL (`FOR UPDATE SKIP LOCKED`) for robust, lock-free queueing semantics, a stateless horizontal-scaling worker fleet in Python (FastAPI), and a modern React + TailwindCSS dashboard for real-time monitoring and administration.

## Features
- **Stateless Worker Fleet**: Horizontal scaling out of the box with zero locking contention.
- **Robust Queueing**: Transactional, atomic job claiming built on PostgreSQL.
- **Advanced Job Lifecycle**: Supports delayed, scheduled, batch, and cron jobs.
- **Resilience**: Configurable exponential backoff retries and Dead Letter Queue (DLQ) routing.
- **Axiom Dashboard**: Beautiful, real-time UI built with React, Tailwind, and driver.js for guided onboarding.

---

## Free & Public Deployment Guide (0 to Live in 5 Minutes)

You can easily deploy Axiom for free on the public internet using platforms like **Render** (for the backend & DB) and **Vercel** (for the frontend).

### Option 1: The "All-in-One Docker" approach (HuggingFace Spaces / Render Docker)
If you want to host the *entire* stack (Frontend, Backend, and Database) together:
1. **Render**: 
   - Sign up for a free account at [Render.com](https://render.com).
   - Create a new "Web Service" -> Connect this GitHub repository.
   - Choose the "Docker" environment. Render will automatically detect the `docker-compose.yml` (Note: for true free-tier, you might need to create a `Dockerfile` that spins up Postgres + API + Nginx together, but Render offers a free managed PostgreSQL).
2. **HuggingFace Spaces**:
   - Create a new Space -> Choose "Docker".
   - You can run the entire `docker-compose` setup using a multi-container Docker space.

### Option 2: The Recommended Decoupled Free Tier (Vercel + Supabase + Render)
For a production-ready, globally accessible deployment for **$0**:

#### Step 1: Database (Supabase)
1. Go to [Supabase](https://supabase.com) and create a free project.
2. Go to Project Settings -> Database -> Copy your **Connection String (URI)**.
3. Replace the local Postgres URI with this string in your backend environments.

#### Step 2: Backend API & Poller (Render)
1. Go to [Render](https://render.com) and create a new **Web Service**.
2. Connect your GitHub repository.
3. Set the Root Directory to `backend/`.
4. Set the build command: `pip install -r requirements.txt`
5. Set the start command: `uvicorn main:app --host 0.0.0.0 --port 10000`
6. Add the Environment Variable: `DATABASE_URL` = (Your Supabase string).
7. Deploy. Note your Render URL (e.g., `https://axiom-api.onrender.com`).

#### Step 3: Frontend Dashboard (Vercel)
1. Go to [Vercel](https://vercel.com) and click **Add New -> Project**.
2. Import your GitHub repository.
3. Set the Root Directory to `frontend/`. Vercel will automatically detect React/Vite.
4. Open **Environment Variables**:
   - Add `VITE_API_URL` = `https://axiom-api.onrender.com/api`
5. Click **Deploy**.

Within 5 minutes, your Axiom dashboard will be publicly accessible worldwide!

---

## Local Development Setup

To run locally with Docker:
```bash
docker compose up -d --build
```
- **Dashboard**: `http://localhost:3000`
- **API Swagger Docs**: `http://localhost:8000/docs`
- **Database**: `localhost:5432`

*Login with `shoryamishra61@gmail.com` / `password` to see the automated interactive tour!*
