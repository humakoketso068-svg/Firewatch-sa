# Firewatch live features: setup

(Section 6 onward covers the emergency-response features: SOS delivery, station console, incident timelines, spread projection, alert settings.)

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
   Wind, humidity and temperature for the spread projection come from Open-Meteo (free, no key) for active fires; the zone cards and trend charts still use simulated weather.

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
  alerts text not null default 'off',
  prefs text default '{}'
);

-- Already created subscribers earlier?  Run:  alter table subscribers add column if not exists prefs text default '{}';

create table if not exists alert_log (
  key text primary key,
  created_at timestamptz not null default now()
);

create table if not exists report_votes (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  report_id text not null,
  voter_id text not null
);

-- One row per fire / SOS / station notice, with its timeline kept as JSON text.
create table if not exists incidents (
  id text primary key,
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  kind text not null,            -- fire | sos | fpa | rescue
  status text not null,
  title text, place text,
  lat double precision, lon double precision,
  events text default '[]',
  data text default '{}'
);

-- Every message Firewatch sent. Holds a hashed id, never an email or phone number.
create table if not exists message_log (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  who text, kind text, channels text, place text, km integer
);

-- Lock the tables: only the server's service_role key can read or write them.
alter table reports enable row level security;
alter table subscribers enable row level security;
alter table alert_log enable row level security;
alter table report_votes enable row level security;
alter table incidents enable row level security;
alter table message_log enable row level security;
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

## 5. Real place names and exact coordinates (townships, villages, rural areas)
The map ships with 83 sensor towns. To search and label **every** named place in all nine
provinces, build the place list once on your own computer (it needs internet):

```
python build_places.py
```

It downloads the free GeoNames gazetteer for South Africa and writes `places.json` next to
`main.py` (a few MB). It prints how many places it found per province and checks a few names
(for example Lerome). Then commit `places.json` with the rest of the project.

What you get:
- **Search box:** type a town, township or village (Enter picks the first match). Results show
  the province and exact coordinates, and the map zooms there.
- **Labels:** zoom in past about 400% and real place names appear, biggest first, without overlapping.
- **Tap the map** (zoomed in): a card shows the nearest named place, its province, exact
  coordinates, and the nearest sensor town. "Report smoke or fire here" sends a report for that spot.
- **Reports:** the report dialog now names the nearest real place and shows the coordinates.

Notes:
- GeoNames is community data. Some rural settlements are missing or slightly off. Please check
  places that matter to you. Data licence: CC BY 4.0 (the app footer credits GeoNames).
- Without `places.json` everything else still works and search covers the 83 sensor towns only.
- `python build_places.py --min-pop 500` keeps only places with 500+ people (smaller file).
- It also works on the Netlify build, because it needs no server, but it makes the first load bigger.

## 6. Real SMS delivery (South African providers)
Pick **one**; Firewatch uses the first that is configured (or force one with `SMS_PROVIDER=bulksms|clickatell|twilio`).

| Provider | Variables | Notes |
|---|---|---|
| BulkSMS (bulksms.com) | `BULKSMS_TOKEN_ID`, `BULKSMS_TOKEN_SECRET` | Create an API token in your BulkSMS account. Pay-as-you-go credits. |
| Clickatell | `CLICKATELL_API_KEY` | One API integration key. |
| Twilio | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` | Trial accounts only text verified numbers. |

**What "sent" means.** The status shown after an SOS or an alert (for example "Sent by SMS at 23:52 (accepted by the
provider)") means the SMS provider accepted the message. It does not prove that a person read it, and Firewatch never
claims a station "received" anything it cannot confirm. A station acknowledging in the Station console is the real
confirmation, and that shows up on the SOS screen too.

Every message is recorded: SOS deliveries and acknowledgements in the incident timeline, alert messages in `message_log`
(hashed id only), and each person can see their own recent messages in Alert settings.

## 7. Fire station directory (needs your input: I cannot invent this data)
The built-in stations are **illustrative samples** and are never messaged. For SOS messages to reach a real crew:
1. Copy `stations_template.csv`, and add one row per station (name, province, lat, lon, phone, area).
2. Phone or email each station. Ask if they want Firewatch SOS messages, and on which cell number or mailbox.
   Fill in `sms` / `email` only with their agreement, put what you did in `source` ("phoned 14 Nov, spoke to ..."),
   and only then set `verified` to `yes`.
3. Run `python build_stations.py stations.csv`. It writes `stations.json` and tells you how many stations can receive
   SOS messages. Commit `stations.json`.

Firewatch messages a station only if it is verified and has an SMS number or email. Otherwise the caller is told plainly
"no station near you can be messaged directly, call 112". Good sources for the list: municipal websites, the
Fire Protection Association (FPA) lists on the Southern African Wildfire Association / provincial pages, and
OpenStreetMap `amenity=fire_station` for coordinates.

## 8. Station console and FPA notices
Set `STATION_KEY=somelongsecret` (one shared key) or `STATION_KEYS=Komatipoort:key1,Nelspruit:key2` (one per station) on
Render. Share each key privately with that station. Menu > **Station console**:
- **Incoming SOS requests**: caller, place, GPS, address, notes. Buttons: Acknowledge, Crew dispatched, Resolved. The caller's
  screen shows "Acknowledged by Komatipoort Fire & Rescue" within seconds.
- **Post a notice**: a fire status (Active, Evacuation warning, Contained, Extinguished) or a road / rescue flag
  (including "extrication equipment needed", Jaws of Life). It appears on the public map and in the incident list,
  and, for fire notices, can SMS / email subscribers within 5-50 km. This digitises what FPAs now do on WhatsApp groups.
Keys are compared in constant time and five wrong tries lock the form for a minute. Treat the key like a password: anyone who
has it can see caller phone numbers.

## 9. Incident timelines
Menu > **Incidents and timelines**. A fire incident is opened automatically the first time NASA detects fire near a town. Its
timeline records: first detection, growth, when alerts went to nearby subscribers (counts, not names), "no new detections",
and closure. Satellite data **cannot** say a fire is out, so "Closed" means 36 hours with no detections; only a station can
mark a fire Contained or Extinguished. SOS incidents are only visible in the Station console, never in the public list.

## 10. Fire-spread projection
Active fires show a faded red ellipse (long axis downwind) and an arrow: where the fire could reach in the next 3 hours.
Tap or hover for the numbers. It uses wind speed and direction, fuel moisture (from temperature and humidity) and slope.
For real NASA fires the server fetches the actual forecast from Open-Meteo; in simulation mode it uses the simulated weather.
It is an **indicative** model (the standard elliptical-growth shape, simplified), not an operational forecast: it ignores fuel
type, firebreaks, firefighting and fine terrain. Do not use it to decide whether to evacuate. Hidden in data-saver mode.

## 11. Alert settings, languages and emergency contacts
Menu > Alert settings and contacts (or Profile). People choose: how strong a fire to be alerted about, distance from their place
(5-100 km), quiet hours (strong fires still come through), language (English, Afrikaans, isiZulu, Setswana, Sesotho), and up to
three **emergency contacts** who get an SMS when the person presses SOS.
The isiZulu, Setswana, Sesotho and Afrikaans texts are drafts for the safety-critical sentences only. Have first-language speakers
check them before real use (`i18n.py`). The "What to do now" checklists and the rest of the screens are English only for now.

## 12. Verified reports and house / informal-settlement fires
Reports now include "House or building fire" and "Informal settlement fire" with an address field. A report is marked **verified**
when a NASA hotspot is within 5 km (detected within 12 h of it) or when two other people press "I can see this too" on it. Unverified
pins are drawn paler. You cannot confirm your own report. **Photo upload is not built**: it needs file storage (Supabase Storage)
plus content moderation, which is a larger step.

## 13. Evacuation information
Menu > **What to do now** (also reachable from the SOS result screen): a checklist for veld fires, house fires and informal
settlement fires, plus the nearest hospitals and assembly points from OpenStreetMap. Volunteer-mapped data is incomplete in rural
areas, so the screen says so and links to a live map search. Official evacuation routes are not published as open data in South
Africa; they are announced by police, fire services and municipalities. The app does not draw routes it cannot verify.

## 14. Privacy by design
- Subscriber positions are stored rounded to a ~5 km grid (`alerts.PRIVACY_STEP`), so a database leak cannot show a house.
- Message logs keep a hashed id, not email or phone.
- SOS keeps the exact location (a crew needs it) but only the Station console can see it.
- Passwords are salted and hashed; reports show only a first name.

## 15. Not built yet (be honest in your demo)
- **USSD** (for phones without data) needs a telecom aggregator account and a shortcode (for example through Clickatell or a
  mobile network). SMS alerts already work on any phone; two-way SMS and USSD are a next step.
- **Photo upload** for reports (see 12).
- **Official fire-station register**: you must collect and verify it (see 7).
- **Real wind for the zone cards and trend charts**; only the spread projection uses the forecast.

## Deploy
Push to GitHub, then Render > New > Blueprint (reads `render.yaml`). If you made the service by hand, set Build Command to `pip install -r requirements-server.txt` and Start Command to `python main.py` and fill in the secrets it asks for.
After changing environment variables, Render restarts the service by itself.

## Privacy notes
- Alerts store each subscriber's email, phone number, name and home town on your Supabase database.
  Tell users (the dialogs do) and delete rows on request.
- Citizen reports are public and unverified, and show the reporter's first name only.
- Reports need a login, are limited to 5 per person per hour and to places inside South Africa.
