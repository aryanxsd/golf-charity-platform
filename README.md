# Golf Charity Subscription Platform

PRD-aligned full-stack demo for the Digital Heroes trainee assignment, built with Flask.

It now supports:

- Local development with SQLite
- Production-style deployment with Supabase Postgres via `DATABASE_URL`
- Vercel deployment through the included Python entrypoint

## What is included

- Public homepage with clear CTA, charity spotlight, and prize-impact messaging
- Subscriber signup/login flow with monthly and yearly plan activation
- Restricted access for non-subscribers on score-entry features
- Stableford score management with strict 1-45 validation and rolling latest-5 logic
- Charity directory with search, filters, profile pages, and independent donation flow
- Monthly draw engine with random or algorithmic modes, simulation, publish, and jackpot rollover
- Winner verification workflow with proof upload and payment-state tracking
- Subscriber dashboard for subscription, scores, charity settings, participation, winnings, and notifications
- Admin dashboard for users, subscriptions, scores, charities, draws, winners, and analytics

## Assumptions

- Payments are still mocked locally rather than connected to Stripe.
- Notifications are still stored in-app as a delivery log instead of sending real emails.
- Prize pool uses `40%` of active subscription revenue, then splits that pool into:
  - 5-match: 40%
  - 4-match: 35%
  - 3-match: 25%
- A subscriber's draw ticket is derived from their latest five saved Stableford scores.

## Run locally

```bash
python app.py
```

Then open `http://127.0.0.1:5000`.

## Supabase setup

1. Create a new Supabase project.
2. Open the SQL editor.
3. Run the contents of `schema_postgres.sql`.
4. Copy the Postgres connection string into `DATABASE_URL`.
5. Set a strong `SECRET_KEY`.

The app automatically uses Postgres when `DATABASE_URL` starts with `postgres://` or `postgresql://`.

## Vercel deployment

1. Create a new Vercel project from this folder/repo.
2. Vercel will use `vercel.json` and `wsgi.py`.
3. Add these environment variables in Vercel:
   - `SECRET_KEY`
   - `DATABASE_URL`
   - `FLASK_ENV=production`
4. Deploy.

Health check endpoint:

- `/health`

## Demo credentials

- Admin:
  - Email: `admin@golfcharity.local`
  - Password: `admin12345`

## Useful demo route

- Visit `/seed-demo` once to generate sample subscribers, subscriptions, and scores.

## Project structure

- `app.py`: Flask routes, business logic, and dashboard workflows
- `schema.sql`: SQLite schema
- `schema_postgres.sql`: Supabase/Postgres schema
- `templates/`: Page templates
- `static/styles.css`: Responsive styling
- `uploads/`: Winner-proof uploads
- `vercel.json`: Vercel Python deployment config
- `wsgi.py`: Vercel/WSGI entrypoint
- `PRD_CHECKLIST.md`: build completion and QA checklist
