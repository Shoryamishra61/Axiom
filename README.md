# Axiom: Distributed Job Scheduler

**Axiom** is a high-performance, fault-tolerant distributed job scheduling and monitoring platform. Engineered for robustness, strict consistency, and horizontal scalability, it serves as a foundation for executing asynchronous workloads with complex lifecycle requirements (immediate, delayed, scheduled, recurring cron, and batch execution).

---

## 1. Project Description

Modern web and microservice architectures require reliable background task execution. Axiom provides a robust queueing semantic built entirely on PostgreSQL. By avoiding external message brokers (such as Redis or RabbitMQ), it significantly reduces infrastructure complexity and points of failure while maintaining strict ACID transactional guarantees for job state.

The platform is divided into three primary components:
1. **REST API (FastAPI):** A high-throughput, non-blocking interface for job submission, queue administration, and metrics retrieval.
2. **Worker Fleet (Python):** A completely stateless, horizontally scalable pool of worker processes that poll for jobs using concurrency-safe database locks.
3. **Axiom Dashboard (React + Vite):** A real-time, low-latency administrative interface for monitoring queues, analyzing job execution, and managing Dead Letter Queues (DLQ).

---

## 2. Architecture & System Design

### 2.1 Component Architecture
Axiom operates on a decoupled, stateless microservice paradigm.

*   **Frontend (Dashboard):** Built as a Single Page Application (SPA) using React and Tailwind CSS. It communicates purely via REST over HTTP.
*   **API Node:** A FastAPI server running on Uvicorn. It exposes endpoints for queue management, job creation, and worker introspection.
*   **PostgreSQL Engine:** The sole source of truth. It stores queue configurations, job payloads, execution history, and worker heartbeats.
*   **Worker Nodes:** Independent Python processes running infinite polling loops. They are stateless; they can be forcefully terminated and auto-scaled dynamically without cluster coordination.

### 2.2 Concurrency & Locking Mechanics
To achieve highly concurrent, lock-free queueing without a dedicated broker, Axiom utilizes PostgreSQL's `SELECT ... FOR UPDATE SKIP LOCKED`. 
*   **Strict Isolation:** When a worker attempts to claim a job, the database locks the selected row.
*   **Non-Blocking:** If a second worker polls simultaneously, `SKIP LOCKED` instructs the database to instantly bypass the locked row and fetch the next available job, eliminating contention and deadlocks.
*   **Atomic State Transitions:** Job claims, status updates, and retry increments are performed within isolated transactions.

---

## 3. Core Features & Job Lifecycle

### Job Types
*   **Immediate:** Executed as soon as a worker is available.
*   **Delayed/Scheduled:** Held in a pending state until a specific `run_at` UTC timestamp.
*   **Cron:** Recurring workloads defined by UNIX cron expressions. A background materializer process periodically evaluates the cron schedule and spawns concrete jobs.
*   **Batch:** Atomic submission of multiple payloads grouped under a single execution context.

### Fault Tolerance & Retry Strategies
When a job fails (e.g., due to an external API timeout or transient exception), it is subject to configurable retry policies:
*   **Fixed Backoff:** Retries after a constant time delay.
*   **Linear Backoff:** Delay increases linearly with each attempt.
*   **Exponential Backoff with Jitter:** Delay doubles exponentially, introducing random jitter to prevent "thundering herd" synchronization against downstream services.

### Dead Letter Queue (DLQ)
Jobs that exhaust their maximum configured retry attempts are automatically moved to a terminal `dead` state. The Axiom Dashboard provides a dedicated UI to inspect these failures and manually requeue them once the underlying issue is resolved.

---

## 4. Design Decisions and Major Trade-Offs

**1. PostgreSQL vs. Dedicated Brokers (RabbitMQ, Redis, Kafka)**
*   *Decision:* Built the queue entirely in PostgreSQL.
*   *Trade-off:* Dedicated brokers offer sub-millisecond latencies and can handle millions of messages per second via in-memory pub/sub. However, they lack strict ACID guarantees for relational state. By using PostgreSQL, we trade extreme microsecond latency for absolute data integrity, historical persistence, and massive reductions in infrastructure maintenance. For the vast majority of enterprise workloads (up to 10k jobs/sec), PostgreSQL provides more than adequate throughput.

**2. Polling vs. Push Streams**
*   *Decision:* Workers pull jobs on a polling interval rather than receiving pushed streams via WebSockets or long-polling.
*   *Trade-off:* Pulling introduces a minor latency penalty (equal to the polling interval). However, push architectures require complex connection management, sticky sessions, and cluster coordination. The stateless pull architecture allows workers to scale infinitely, handle unexpected crashes gracefully (reaper processes clean up orphaned jobs), and deploy across separate geographic regions effortlessly.

**3. SPA Dashboard vs. SSR (Server-Side Rendering)**
*   *Decision:* The frontend is a static Vite/React application.
*   *Trade-off:* Frameworks like Next.js provide Server-Side Rendering (SSR) which drastically improves SEO and initial layout paint times. Because Axiom is an internal administration console behind authentication, SEO is irrelevant. A static SPA simplifies the deployment model to a simple CDN or Nginx server without requiring a Node.js runtime.

---

## 5. Automated Verification

The system is rigorously verified via an automated `pytest` suite ensuring distributed integrity:
*   **Concurrency Tests (`test_concurrency.py`):** Spawns multi-threaded worker simulations to guarantee that `SKIP LOCKED` prevents duplicate job claims under heavy load.
*   **Idempotency Tests (`test_idempotency.py`):** Ensures that identical jobs submitted with identical idempotency keys are mathematically deduplicated.
*   **Retry Math (`test_retry_math.py`):** Unit tests verifying that exponential backoff and jitter algorithms calculate precise future timestamps.

---

## 6. Free & Public Deployment Guide (Live in 5 Minutes)

You can deploy Axiom publicly for free using a decoupled cloud architecture (Vercel + Supabase + Render).

### Step 1: Database (Supabase)
1. Go to [Supabase](https://supabase.com) and create a free PostgreSQL database.
2. Navigate to Project Settings -> Database -> Copy your **Connection String (URI)**.
3. Make sure to append `?sslmode=require` if it's not already in the connection string.

### Step 2: Backend API & Workers (Render)
1. Go to [Render.com](https://render.com) and click **New -> Web Service**.
2. Connect this GitHub repository.
3. **CRITICAL:** Set the **Root Directory** to `backend` (without the slash, just type `backend`).
4. Set the **Language/Environment** to `Python` (Do NOT select Docker, as Render expects a single root Dockerfile by default).
5. Set the **Build Command** to: `pip install -r requirements.txt`
6. Set the **Start Command** to: `uvicorn main:app --host 0.0.0.0 --port $PORT`
7. Add an Environment Variable: `DATABASE_URL` = *(Your Supabase connection string)*.
8. Deploy, and note the resulting API URL (e.g., `https://axiom-api.onrender.com`).

### Step 3: Frontend Dashboard (Vercel)
1. Go to [Vercel](https://vercel.com) and click **Add New -> Project**.
2. Import this GitHub repository.
3. **CRITICAL:** Set the **Root Directory** to `frontend`. Vercel will automatically detect React and Vite.
4. Under Environment Variables, add: `VITE_API_URL` = `https://axiom-api.onrender.com/api` (Make sure to append `/api` to your Render URL).
5. Click **Deploy**.

*Within minutes, the Axiom dashboard will be publicly accessible worldwide!*

---

## 7. Local Development & Demo

To spin up the entire stack locally using Docker Compose:

```bash
# Start PostgreSQL, API, Dashboard, and Worker Nodes
docker compose up -d --build
```

*   **Axiom Dashboard:** `http://localhost:3000`
*   **REST API Swagger:** `http://localhost:8000/docs`

**Test Account Credentials (Pre-filled in UI):**
*   **Email:** `shoryamishra61@gmail.com`
*   **Password:** `password`
