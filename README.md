# Firewatch — South Africa Wildfire Early-Warning Console (Flet)

A cross-platform dashboard for a simulated wildfire sensor network, written
entirely in Python. One codebase runs on Windows, macOS, Linux, Android, iOS
and the web.

## What's simulated

- 83 sensor nodes across all nine provinces of South Africa (cities, towns, mountain and
  bushveld areas such as the Cape winelands, Drakensberg, Kruger and the Kgalagadi), with
  temperature, humidity and fuel-moisture readings that drift over time
- A map of South Africa with the Lesotho and eSwatini enclaves and province names
- A risk score per zone from wind speed, fuel moisture, temperature and slope
- Random ignitions weighted toward high-risk zones, with a spread ellipse oriented by
  wind direction and a dashed evacuation-advisory ring on extreme fires
- Containment over time, a live event feed, and wind / fuel-moisture trends
- A public alert view: the same data as a plain-language advisory
- **Emergency button** (header, floating button and fire-alert bar) that alerts every fire station
  near a chosen location, shows them on the map with distance and ETA, and logs the alert to the feed
- **Sign up / log in / profile** dialogs (name, email, mobile, nearest town, password)
- **Zoomable map**: + / - buttons, mouse wheel, pinch, drag to pan, double-click to zoom, a
  "Find a place" search, "zoom to active fires", a scale bar, and place names that appear as you zoom in

## Files

All Python code is in the `src/` folder. At the project root: `pyproject.toml` (build settings), `requirements.txt`, and `.github/workflows/deploy.yml` (Vercel deploy).

| File | Role |
|------|------|
| `geo.py` | Geography: the South Africa outline, province labels and the latitude/longitude to map projection. |
| `simulation.py` | The engine. Plain Python, no UI. `tick()` advances it, `snapshot()` returns the state. |
| `main.py` | The Flet interface: header, console, public view, app loop. |
| `firemap.py` | The interactive map (zoom, pan, labels, fire-station overlay). |
| `dialogs.py` | Sign up, log in, profile and emergency-alert dialogs. |
| `auth.py` | Account storage (`~/.firewatch/users.json`, salted PBKDF2 password hashes). |
| `stations.py` | Fire-station list and nearest-station search. |
| `ui.py` | Theme colours and small UI helpers. |
| `requirements.txt` | `flet` |

The UI only ever reads `snapshot()`, so real sensor / weather / satellite data can replace
`Simulation._step_environment` without touching `main.py`.

## Run it
```bash
pip install -r requirements.txt
python src/main.py
```

The layout is responsive: three columns on wide windows, a single scrolling column on
tablets and phones.

## Deploy to Vercel

Vercel can't run Flet's normal Python server (it only runs short serverless functions, not a
long-lived app with live updates). So the web build runs the Python **inside the browser**
(`flet build web`), which produces a static site that Vercel hosts happily.

**Easiest way: let GitHub build and deploy it (nothing to install on your PC)**

1. Put this project on GitHub, with `pyproject.toml`, `src/` and `.github/` at the top level.
2. On vercel.com go to Account Settings > Tokens and create a token. Copy it.
3. On GitHub open your repo > Settings > Secrets and variables > Actions > New repository secret.
   Name it `VERCEL_TOKEN` and paste the token.
4. Push to `main` (or open the Actions tab and run "Deploy to Vercel"). The first build takes
   several minutes because Flet downloads its build tools. The live address is printed at the end of
   the "Deploy to Vercel" step and appears in your Vercel dashboard as the project `firewatch`.

**Or from your own PC**

```bash
pip install "flet[all]"
flet build web                 # creates build/web
npx vercel build/web --prod    # follow the prompts
```

Things to know about the web version:

- The first visit takes a few seconds while the browser loads Python.
- Sign-ups are saved in each visitor's own browser, not on a server, so an account made on one
  device does not exist on another. For real shared accounts, connect a hosted database / auth
  service in place of `auth.py`.
- The emergency alert is still a simulation (see Notes).
- Prefer a normal always-on Python server? `main.py` also runs on Render or Railway, which set `PORT`.

## Package it

Install Flet, then build for your target platform:

- **Windows / macOS / Linux:** `flet build windows` (or `macos`, `linux`)
- **Android:** `flet build apk` (or `flet build aab` for the Play Store)
- **iOS:** `flet build ipa` (requires a Mac with Xcode)
- **Web:** `flet build web`

Run these from the project root. Build settings such as the app name, version,
and dependencies go in `pyproject.toml` (or via flags like `--project` and
`--product`).

## Adding or moving places

Places live in `ZONE_DEFS` at the top of `simulation.py`:

```python
# id, name, province, lat, lon, elev, slope
("z84", "Hluhluwe", "KwaZulu-Natal", -28.02, 32.05, 0.10, 0.20),
```

Use real latitude/longitude (South Africa is roughly lat -22 to -35, lon 16 to 33).
`elev` and `slope` are 0 to 1; slope feeds the risk score. To print a place's name on the map,
add it to `LABELLED` in `geo.py`. Ignition odds scale automatically with the number of nodes.

## Notes

- **The emergency alert is a simulation.** It does not call, text or email anyone. Fire-station
  names and positions in `stations.py` are illustrative, not an official register. To make it real,
  replace `build_stations()` with a real dataset and the "contacting" loop in `dialogs.py` with an
  SMS / call / dispatch-API integration. In a real emergency dial 112 from a cell phone.
- Accounts are stored locally for this demo. For multiple users on different devices, use a
  hosted backend instead of `auth.py`.

- The outline in `geo.py` is simplified and stylised, not a survey-grade border.
- The simulation runs in-process on Flet's clock (every 2.2 s). There is no server, so the app
  works offline and on mobile.
- To go beyond a prototype, swap the toy risk formula for a validated fire-danger index (e.g., NFDRS)
  and the spread model for a physics-based one (e.g., Rothermel).
