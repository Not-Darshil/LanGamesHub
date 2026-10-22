# Offline installation on the Windows host

The host PC never needs internet access. You prepare a bundle on an internet-connected
development PC, copy it over (USB drive, network share), and install from it.

## 1. Build the bundle (development PC, online)

Prerequisites on the dev PC: Python 3.11, [uv](https://docs.astral.sh/uv/), Node.js,
`zip`, and this repository.

```sh
scripts/build-bundle.sh 1.0.0
```

This:

1. builds the React frontend (`npm ci && npm run build`) and fails if the build
   references any remote URL;
2. downloads **every pinned Python dependency** for Windows x64 / CPython 3.11 into
   `wheelhouse/` (packages published only as source, such as `chess`, are built into a
   universal pure-Python wheel from the pinned source);
3. proves the wheelhouse is complete by resolving the full install for Windows with
   `pip --no-index`;
4. assembles `dist-bundle/LanGamesHub-1.0.0/` with a `MANIFEST.sha256`, and zips it.

Bundle contents:

```
LanGamesHub-1.0.0/
  backend/            application code, Alembic migrations, pinned requirements
  frontend/dist/      built web UI
  wheelhouse/         all Python wheels (offline install source)
  windows/            install / migrate / start / diagnose / backup / restore scripts
  docs/  README.md  .env.example  MANIFEST.sha256
```

## 2. Prerequisites on the host

* **Python 3.11 (64-bit)** is installed. The installer looks for `py -3.11`, then
  `python` (if it is 3.11).
* **PostgreSQL** is installed and running. You need a database and a login role that can
  create tables in it. For example, in pgAdmin or `psql` as an administrator:

  ```sql
  CREATE ROLE langameshub LOGIN PASSWORD 'choose-a-strong-password';
  CREATE DATABASE langameshub OWNER langameshub;
  ```

  LanGamesHub does **not** change PostgreSQL's configuration (`postgresql.conf`,
  `pg_hba.conf`, services). If PostgreSQL runs on the same PC, `localhost` works with the
  default configuration.

## 3. Install (host, offline)

1. Unzip the bundle, e.g. to `C:\LanGamesHub`. Optionally verify integrity:
   `certutil -hashfile <file> SHA256` against `MANIFEST.sha256`.
2. Run **`windows\install.bat`**. It creates `backend\.venv` and installs the packages
   with `pip install --no-index --find-links wheelhouse` (nothing is downloaded). It
   also creates `.env` from `.env.example` if `.env` does not exist yet.
3. Edit **`.env`**:
   * `DATABASE_URL=postgresql+psycopg://langameshub:<password>@localhost:5432/langameshub`
   * the room password: run `windows\hash-password.bat` and paste the
     `ROOM_PASSWORD_HASH=` line (then delete the `ROOM_PASSWORD=` line), or set
     `ROOM_PASSWORD` directly;
   * `ADMIN_PASSWORD` (8+ characters) for the first admin login.

   The server refuses to start while the example passwords from `.env.example` are
   still in place.
4. Run **`windows\migrate.bat`** to create the tables.
5. Run **`windows\diagnose.bat`**. Every line should be `[PASS]` (a `WARN` about the
   plaintext room password is fine if you chose that). It prints the guest URL(s).
6. Run **`windows\start.bat`** and keep the window open. The log shows
   `Guests open http://192.168.x.y:8000 · host dashboard http://192.168.x.y:8000/admin`.

## 4. Allow guests through the firewall

The first time Python listens on the network, Windows Defender Firewall may ask whether
to allow it. Choose **Private networks** only. To add the rule yourself instead (in an
Administrator command prompt):

```bat
netsh advfirewall firewall add rule name="LanGamesHub" dir=in action=allow protocol=TCP localport=8000 profile=private
```

Make sure the LAN connection's network profile is **Private**, not Public.

## 5. First use

1. On the host, open `http://localhost:8000/admin` and log in with `ADMIN_USERNAME` /
   `ADMIN_PASSWORD`. After the first successful start you may remove `ADMIN_PASSWORD`
   from `.env`.
2. Tell guests the URL and the room password. Approve them as they arrive.
3. Create a room, wait for players to join and click "I'm ready", then press **Start
   game**.
4. To play yourself, use **Open player view** on the dashboard (a new tab with your own
   player identity).

## Upgrading

1. Back up (`windows\backup.bat`) and stop the server (Ctrl+C in the `start.bat` window).
2. Unzip the new bundle to a **new** folder and copy your `.env` into it.
3. Run `windows\install.bat`, then `windows\migrate.bat`, `windows\diagnose.bat`,
   `windows\start.bat` from the new folder.
