# Auth + Billing Setup Runbook

> Phase 5a infrastructure runbook for provisioning Supabase Auth + Stripe Billing for SeestarScope.
> Run through these steps once per environment (test / prod). Phase 5b–5e application code reads
> the resulting credentials from the env-var contract defined in `.env.example`.

## Overview

| Step | What you provision | Credentials captured |
|------|--------------------|----------------------|
| 1 | Supabase project + Email + Google OAuth | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` |
| 2 | Stripe test-mode prices + webhook endpoint | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_WATCH_PRICE_ID`, `STRIPE_CONTROL_PRICE_ID` |
| 3 | Supabase Stripe Sync Engine | (verification only — mirror tables in Postgres) |
| 4 | Fill in `.env` on Jetson and rebuild | — |

---

## 1. Supabase Provisioning

1. Sign in at <https://supabase.com> and click **New Project**.
   - Name: `seestar-scope-<env>` (e.g. `seestar-scope-prod`)
   - Region: pick the one closest to your Jetson
   - Database password: generate and store in a password manager
2. Wait for the project to provision (~2 min).
3. **Enable Email auth**:
   - **Authentication → Providers → Email**
   - Toggle **Enable Email provider** on
   - Toggle **Confirm email** on (production); off is acceptable for local dev only
4. **Enable Google OAuth**:
   - **Authentication → Providers → Google** — toggle on
   - Create a Google Cloud OAuth client (Web application) at
     <https://console.cloud.google.com/apis/credentials>
     - Authorized redirect URI: `<SUPABASE_URL>/auth/v1/callback`
   - Paste the **Client ID** and **Client Secret** into the Supabase Google provider form
   - Click **Save**
5. **Capture the 4 keys**:
   - **Settings → API**
     - `SUPABASE_URL` — the *Project URL* (`https://<project-ref>.supabase.co`)
     - `SUPABASE_ANON_KEY` — the *anon / public* key
     - `SUPABASE_SERVICE_ROLE_KEY` — the *service_role* key (treat as a database password)
   - **Settings → API → JWT Settings**
     - `SUPABASE_JWT_SECRET` — the JWT secret used to verify access tokens server-side

> The `service_role` key and JWT secret bypass row-level security. Never ship them to the
> browser. They are read only by the FastAPI backend.

---

## 2. Stripe Setup (test mode)

1. Sign in at <https://dashboard.stripe.com> and toggle **Test mode** in the top-right.
2. **Create the Watch product (recurring monthly)**:
   - **Products → Add product**
   - Name: `SeestarScope Watch`
   - Pricing: **Recurring**, **Monthly**, amount `$9.99 USD`
   - Save and capture the price ID (`price_...`) → this is `STRIPE_WATCH_PRICE_ID`
3. **Create the Control product (metered, per-hour)**:
   - **Products → Add product**
   - Name: `SeestarScope Control`
   - Pricing: **Recurring**, **Usage-based / Metered**, amount `$14.99 USD` per unit, billing period
     monthly (units are reported as hours of telescope time)
   - Save and capture the price ID → this is `STRIPE_CONTROL_PRICE_ID`
4. **Capture the API key**:
   - **Developers → API keys**
   - Reveal the **Secret key** (`sk_test_...`) → `STRIPE_SECRET_KEY`
5. **Configure the webhook endpoint** (Phase 5c implements the handler; just register the URL):
   - **Developers → Webhooks → Add endpoint**
   - Endpoint URL: `https://<jetson-public-hostname>/api/webhooks/stripe`
     (placeholder OK until Phase 5c lands)
   - Events to listen for: `customer.subscription.*`, `invoice.*`, `checkout.session.completed`
   - Save and reveal the **Signing secret** (`whsec_...`) → `STRIPE_WEBHOOK_SECRET`

---

## 3. Supabase Stripe Sync Engine

The Sync Engine mirrors Stripe objects (customers, subscriptions, invoices) into Supabase Postgres
so the FastAPI backend can query a single source of truth.

1. **Install** (Supabase Pro plan):
   - **Database → Extensions → Marketplace**
   - Find **Stripe Sync Engine**, click **Install**
   - Paste your `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` when prompted
2. **Free-tier workaround** (skip if on Pro):
   - Enable the `pg_net` extension manually under **Database → Extensions**
   - Follow the upstream README at <https://github.com/supabase/stripe-sync-engine> to
     deploy the sync function as a Supabase Edge Function
3. **Verify mirror tables exist** — after installation, send a Stripe test webhook
   (`stripe trigger customer.subscription.created`) and confirm in the Supabase SQL editor:

   ```sql
   select count(*) from stripe.customers;
   select count(*) from stripe.subscriptions;
   select count(*) from stripe.invoices;
   ```

   Each table should be present (even if empty before the first event).

---

## 4. Filling in `.env` on the Jetson

1. SSH to the Jetson: `ssh jmm2020@192.168.0.234`
2. Copy the template if no `.env` exists yet:
   ```bash
   cd ~/seestar-scope
   cp .env.example .env
   ```
3. Edit `.env` and paste the 8 values captured above:
   ```
   SUPABASE_URL=https://<project-ref>.supabase.co
   SUPABASE_ANON_KEY=<anon-key>
   SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
   SUPABASE_JWT_SECRET=<jwt-secret>
   STRIPE_SECRET_KEY=sk_test_<...>
   STRIPE_WEBHOOK_SECRET=whsec_<...>
   STRIPE_WATCH_PRICE_ID=price_<watch>
   STRIPE_CONTROL_PRICE_ID=price_<control>
   ```
4. Rebuild and restart the stack:
   ```bash
   docker compose build
   docker compose up -d
   ```
5. Verify the backend loaded the new env vars:
   ```bash
   docker exec seestar-portal-backend python -c \
     "from config import settings; print(bool(settings.supabase_url))"
   ```
   Expect `True`. Phase 5b–5e features will become reachable once their code lands.

---

## Notes

- Test mode vs. live mode: keep two Stripe `.env` files locally (`/etc/seestar-scope/.env.test`,
  `.env.live`) and symlink the active one. Switching modes requires rotating all 4 Stripe values
  *and* restarting the backend container.
- The 6 required secrets (`SUPABASE_*`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`) raise
  `ValueError` when accessed through `portal/config_loader.py` if missing — the FastAPI backend
  keeps them as `None` so startup never crashes when auth is not yet wired.
- The 2 optional price IDs (`STRIPE_WATCH_PRICE_ID`, `STRIPE_CONTROL_PRICE_ID`) return `None`
  when unset — Phase 5d's entitlement code branches on presence.
