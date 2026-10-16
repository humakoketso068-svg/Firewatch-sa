# Firewatch live features: setup

Four features were added. All need the **server version** (Render). The Netlify build
stays a simulation demo, because a browser-only site cannot keep an API key secret,
run a background alert worker, or share a database.

| Feature | Turns on when | Without it |
|---|---|---|
| Live NASA FIRMS hotspots | `FIRMS_MAP_KEY` is set | simulation |
| Citizen reports | always on (server) | stored in a local file |
| Home-town alerts | Twilio and/or SMTP set | alert menu saves but nothing is sent |
| Data saver | always on | n/a |

## 1. NASA FIRMS key (5 minutes)
1. Open https://firms.modaps.eosdis.nasa.gov/api/map_key/ and request a MAP_KEY with your email.
2. Put it in Render as `FIRMS_MAP_KEY`.
3. Open the app: the "Live NASA data" switch is on and orange dots are real satellite detections.
   Temperature, wind and fuel moisture are **still simulated** (no weather source is connected yet).

## 2. Supabase database (10 minutes)
Without it, reports and subscribers live in a file that **Render's free plan erases on restart**.
1. Create a free project at https://supabase.com.
2. SQL Editor > New query > paste and run:

```sql
create table if not exists reports (
  id text primary key,
  created_at timestamptz not null default now(),
  lat double precision not null,
  lon double precision not null,
  kind text not null,
  note text default '',
  reporter text default '',
  reporter_id text not null
);
create index if not exists reports_created_idx on reports (created_at desc);

create table if not exists subscribers (
  email text primary key,
  created_at timestamptz not null default now(),
  name text, phone text, zone_id text, zone_name text,
  lat double precision, lon double precision,
  alerts text not null default 'off'
);

create table if not exists alert_log (
  key text primary key,
  created_at timestamptz not null default now()
);

-- Lock the tables: only the server's service_role key can read or write them.
alter table reports enable row level security;
alter table subscribers enable row level security;
alter table alert_log enable row level security;
```
3. Settings > API: copy the **Project URL** into `SUPABASE_URL` and the **service_role** key into
   `SUPABASE_SERVICE_KEY`. Never put that key in the app code or in git.

## 3. Alerts
- **SMS:** create a Twilio account, get a number, set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
  `TWILIO_FROM`. A trial account can only text numbers you have verified in Twilio.
- **Email:** set `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` (for Gmail: turn on 2-step verification, then
  create an App Password). `SMTP_PORT` defaults to 587.
- In the app: Menu > Sign up (or My profile) > "Fire alerts for my town" > pick a channel > Save,
  then press **Send me a test alert** to prove your settings work before relying on them.
- Rules: a hotspot within 30 km of the person's town, detected in the last 6 hours, at most one
  message per person every 3 hours, never twice for the same hotspot. Tune with the `ALERT_*` variables.

## 4. Data saver and offline
- The **Data saver** switch slows updates to every ~7 seconds, shortens lists and lightens the map. It
  remembers your choice in the browser.
- If NASA is unreachable the app keeps showing the last downloaded hotspots and says so.
- Real offline use is limited: the app is server-rendered, so it needs a connection to open. (A
  fully offline version would be a separate static build.)

## Deploy
Push to GitHub, then Render > New > Blueprint (reads `render.yaml`) and fill in the secrets it asks for.
After changing environment variables, Render restarts the service by itself.

## Privacy notes
- Alerts store each subscriber's email, phone number, name and home town on your Supabase database.
  Tell users (the dialogs do) and delete rows on request.
- Citizen reports are public and unverified, and show the reporter's first name only.
- Reports need a login, are limited to 5 per person per hour and to places inside South Africa.
