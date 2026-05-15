# TaskGenius

A digital task board for the home. Parents add/edit tasks from their phones; a
mounted screen shows the day's routine (read-only) for the nanny.

- **Display view** (`/`): timeline of today's tasks, big text, auto-refreshes
- **Admin view** (`/admin`): add / edit / delete tasks, phone-friendly

Tech: Python + Flask, SQLite, plain HTML/CSS/JS. Runs on a laptop for
development and on a Raspberry Pi in production.

---

## Local development (laptop)

```bash
# clone (already done if you're reading this from inside the repo)
git clone https://github.com/ayi102/TaskGenius.git taskgenius
cd taskgenius

# virtual env + dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# run
python server.py
```

Then open:

- Display view → http://localhost:5000/
- Admin view  → http://localhost:5000/admin

The SQLite database (`taskgenius.db`) is created automatically on first run and
is gitignored, so each machine keeps its own data.

> **macOS note:** port 5000 is used by AirPlay Receiver by default. Either
> disable it (System Settings → General → AirDrop & Handoff → AirPlay
> Receiver), or run on a different port: `PORT=5050 python server.py`.

---

## Raspberry Pi deployment

These are the steps to install on a fresh Pi (Raspberry Pi OS, Bookworm or
later) and have TaskGenius launch into kiosk mode on boot.

### 1. Get the code on the Pi

```bash
sudo apt update
sudo apt install -y git python3-venv chromium-browser unclutter

cd ~
git clone https://github.com/ayi102/TaskGenius.git taskgenius
cd taskgenius
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Run the server as a systemd service

Create `/etc/systemd/system/taskgenius.service`:

```ini
[Unit]
Description=TaskGenius Flask server
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/taskgenius
ExecStart=/home/pi/taskgenius/venv/bin/python /home/pi/taskgenius/server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable + start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable taskgenius
sudo systemctl start taskgenius
sudo systemctl status taskgenius
```

The display is now reachable at `http://<pi-ip>:5000/`.

### 3. Kiosk mode (auto-launch Chromium full screen)

Create `~/.config/autostart/taskgenius-kiosk.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=TaskGenius Kiosk
Exec=/bin/bash -c "unclutter -idle 0 & chromium-browser --noerrdialogs --disable-infobars --kiosk http://localhost:5000/"
X-GNOME-Autostart-enabled=true
```

Reboot. The Pi will boot into the display view full-screen with no cursor.

Tip: disable screen blanking in `raspi-config` → *Display Options* → *Screen
Blanking* → *Disable*.

---

## Cloudflare Tunnel (edit tasks from anywhere)

To reach the admin view from outside the home network, expose the Pi through a
Cloudflare Tunnel. You'll need a free Cloudflare account and a domain (the
domain is free if you grab one through Cloudflare Registrar, or use any domain
you already own and point it at Cloudflare DNS).

### 1. Install `cloudflared` on the Pi

```bash
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared.deb
```

(Use `cloudflared-linux-armhf.deb` on 32-bit Pi OS.)

### 2. Authenticate and create the tunnel

```bash
cloudflared tunnel login          # opens a browser to authorize the domain
cloudflared tunnel create taskgenius
```

Note the tunnel UUID it prints — you'll need it next.

### 3. Configure routing

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: <TUNNEL_UUID>
credentials-file: /home/pi/.cloudflared/<TUNNEL_UUID>.json

ingress:
  - hostname: tasks.example.com
    service: http://localhost:5000
  - service: http_status:404
```

Point DNS at the tunnel:

```bash
cloudflared tunnel route dns taskgenius tasks.example.com
```

### 4. Run the tunnel as a service

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

The admin view is now reachable at `https://tasks.example.com/admin` from
anywhere.

**Strongly recommended:** protect `/admin` with a Cloudflare Access policy
(Zero Trust dashboard → Access → Applications → Add → Self-hosted) so only
your email addresses can reach it. The app itself has no authentication.

---

## Updating the Pi after pushing new code

```bash
cd ~/taskgenius
git pull
sudo systemctl restart taskgenius
```

The database file is preserved across updates (it's gitignored).

---

## Project layout

```
taskgenius/
├── server.py               # Flask app + SQLite init
├── requirements.txt
├── taskgenius.db           # created on first run (gitignored)
├── templates/
│   ├── display.html        # mounted-screen view (read-only)
│   └── admin.html          # parent CRUD view
└── static/
    ├── css/{display,admin}.css
    └── js/display.js       # auto-refresh + "NOW" highlighting
```