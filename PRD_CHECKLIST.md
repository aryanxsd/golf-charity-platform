# PRD Delivery Checklist

## Completed in this codebase

- Public visitor flows:
  - Homepage explains value proposition, draw mechanics, charity impact, and CTA
  - Charity directory includes search, filter, featured spotlight, and detail pages
- Registered subscriber flows:
  - Signup and login
  - Monthly and yearly subscription activation
  - Profile-level charity selection and contribution percentage
  - Stableford score entry and editing
  - Latest-5 rolling score retention
  - Participation summary and winnings overview
  - Winner proof upload
- Administrator flows:
  - User list and subscription state updates
  - Score editing
  - Charity creation and deletion
  - Draw simulation and publishing
  - Winner verification and payout-state updates
  - Analytics/reporting snapshot
- Draw and prize logic:
  - Random and algorithmic modes
  - Monthly draw model
  - 5 / 4 / 3 match tiers
  - Pre-publish simulation
  - Jackpot rollover when no 5-match winner exists
  - Equal prize split within a winning tier
- UX:
  - Mobile-responsive layout
  - Non-traditional golf visual direction
  - CTA-forward landing page

## Prepared for production handoff

- `DATABASE_URL` support path for Supabase Postgres
- Postgres schema file for Supabase: `schema_postgres.sql`
- Vercel Python deployment config: `vercel.json`
- WSGI entrypoint: `wsgi.py`
- Environment template: `.env.example`

## Still requires real external setup

- Create a new Supabase project and run `schema_postgres.sql`
- Add actual Supabase Postgres connection string to `DATABASE_URL`
- Create a new Vercel project and add environment variables
- Stripe integration is still mocked, not live
- Email notifications are stored in-app, not sent through a provider
- HTTPS enforcement depends on deployment platform configuration

## Recommended final QA

- Signup, login, logout
- Monthly and yearly plan activation
- Lapsed and cancelled subscription behavior
- Six score submissions to confirm latest-5 trimming
- Draw simulation versus publish
- Winner upload, admin approval, and payout state transitions
- Mobile layout on homepage, dashboard, and admin screens
