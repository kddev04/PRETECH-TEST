# Presenting Pretech Connect

Pretech Connect moves data both ways between Microsoft Dynamics 365 Business Central and MySQL.
In the demo, Business Central is simulated on the laptop with Pretech Automation's catalogue
and **sample** figures. The connector code is the same code that will talk to the real tenant.

---

## Part A: on your laptop

### The day before (10 minutes)

1. Open **Docker Desktop** from the Start menu. Wait until the bottom-left says **Engine running**.
2. In File Explorer, open `Desktop\PRETECH\bc-mysql-connector` and double-click **`start-demo.bat`**.
   A black window opens:
   - It shows `Checking MySQL... ready.`
   - Then the box `Pretech Connect is running`.
   - Your browser opens **http://127.0.0.1:8000**.
3. Check the top bar. Both dots must be **green**:
   - **Business Central** · mock tenant · Pretech Automation Pvt. Ltd.
   - **MySQL** 8.4 · bc_sync @ 127.0.0.1:3307
4. Do one full rehearsal, Part A steps 1 to 10 below.
5. Scroll to the bottom of the right-hand panel and click **Reset demo**, then confirm.
   Everything goes back to the starting state.
6. Close the black window to stop. MySQL keeps its container in Docker, which is fine.

### On the day, before he arrives

1. Start Docker Desktop and wait for **Engine running**.
2. Double-click **`start-demo.bat`**.
3. Click **Reset demo** so you start clean. All four cards should show Business Central 8 / 3 / 18 / 5
   and MySQL 0.
4. Make the browser full screen with **F11**. Close every other tab.
5. Keep the laptop on the charger and switch Windows notifications off (Focus assist).

### The presentation (about 12 minutes)

| # | Click | What he sees | What you say |
| --- | --- | --- | --- |
| 0 | — | Top bar with two green dots | "On the left is Business Central, the ERP. On the right is MySQL, where our plant systems live. Pretech Connect sits between them." |
| 1 | **Full pull now** (step 1) | A toast reads "Pulled 34 records…". Cards show 8 / 3 / 18 / 5 on both sides, all **In sync** | "Every customer, vendor, item and sales order is now in MySQL as normal tables, read page by page through Microsoft's standard API." |
| 2 | **Items** tab, then **Sales orders** tab | Pretech's panels (FP-PLC flameproof PLC panel, EP-MCC MCC panel…) and orders with customer POs | "Same item codes and same orders as in BC." |
| 3 | Click the row **FP-PLC** | A side panel compares BC and MySQL field by field, plus the raw BC record | "Every BC field maps to a MySQL column. The full original record is kept too, so nothing is ever lost." Close it with **Close** or **Esc**. |
| 4 | Step 2: Item **FP-PLC**, Unit price, type **499000**, **Save in BC** | The FP-PLC row turns blue: **Changed in BC** | "Someone in accounts changes a price in Business Central." |
| 5 | **Sync now** (top right) | Toast: "1 pulled". The row flashes and goes back to **In sync** at ₹4,99,000 | "Only the changed record travels. That keeps it fast and inside Microsoft's API limits." |
| 6 | Step 3: Item **EP-MCC**, Unit price, type **949000**, **Queue** | EP-MCC shows **Waiting to push**. The **bc_outbox** tab at the bottom has a pending row | "Our own software never touches BC directly. It writes a row in MySQL, and the connector sends it." |
| 7 | **Sync now** | Toast: "1 pushed". The bc_outbox row shows **Done** | "Price updated in Business Central, with an audit trail." |
| 8 | Step 4: type a new customer, for example **Bhima Biotech LLP**, Pune, MH, 1500000, then **Queue**, then **Sync now** | **Customers** tab: new customer **C0009** | "BC gives it a customer number, and that number comes straight back into MySQL." |
| 9 | Step 5: pick **C0003 · Navin Fluorine**, **Set up conflict**, then **Sync now** | The **Activity** tab shows an "ETag conflict… retrying once" line. C0003 has the BC city *and* the MySQL credit limit | "Two people changed the same customer. Nothing is overwritten blindly: it detects the clash and keeps both changes." |
| 10 | Step 6: switch **Simulate throttling** on, then **Sync now**. Switch it off again | The sync takes a few seconds. Activity shows `429 … retrying` lines, then success | "When Microsoft says *too busy*, it waits and retries on its own. No data is lost." |
| 11 | Bottom **SQL on MySQL** tab, then the buttons **Open orders with city**, **Exposure by customer** and **Audit log** | Real query results from MySQL | "This is plain MySQL, so your reports, dashboards and plant software can use it directly." |
| 12 | Top **Auto sync** switch on. Repeat step 4 of this table with another price, then wait about 10 seconds | The change arrives without clicking anything | "In production it runs on its own, every few minutes, or instantly with Business Central webhooks." |

**Close with:** "To connect it to your real Business Central, your admin registers one app in Microsoft
Entra and gives it permission inside BC. We change a few lines in a settings file. There's no
licence or subscription: every part is open source."

**If he asks about cost:** the software is open source, so there are no licence fees. It runs on
any Windows PC or server that can reach MySQL and the internet.

**If he asks about security:**
- **Sign-in:** Microsoft's own sign-in (OAuth 2.0 client credentials).
- **Secrets:** the app secret stays in a local settings file.
- **MySQL access:** only `bc_outbox` can send changes to BC, and every action is logged in the `bc_sync_log` table.

### After the meeting

- Close the black window (or press **Ctrl+C** in it).
- Optional: in Docker Desktop, stop the **pretech-mysql** container.

---

## Part B: on one of his office machines

### What the machine needs

- Windows 10 or 11.
- Internet the first time, to download the libraries and the MySQL image.
- **Python 3.10 or newer** from https://www.python.org/downloads/. In the installer, tick
  **"Add python.exe to PATH"**. Installing may need his IT team.
- One of these for the database:
  - **A. Docker Desktop:** the same as your laptop, and the easiest.
  - **B. Their existing MySQL server:** see B3.
  - **C. Nothing:** the demo falls back to a built-in SQLite file automatically. It's fine for showing
    the flow, but say it's SQLite instead of MySQL.

### B1. Make the package (on your laptop)

```powershell
cd $HOME\Desktop\PRETECH\bc-mysql-connector
.venv\Scripts\python tools\package.py
```

This creates `dist\pretech-connect.zip` (under 100 KB). Copy it to a USB stick, or send it to
yourself by email.

The zip deliberately leaves out your `.venv`, which only works on your laptop. It also leaves out
your `.env` with your passwords, and the APIWORK folder.

### B2. Set up on his machine (5–10 minutes)

1. Copy the zip to the machine, right-click it, choose **Extract All**, and pick `Desktop`.
2. Open `Desktop\pretech-connect` and double-click **`setup.bat`**.
   It ends with `Setup complete. Next: double-click start-demo.bat`.
   - If it says Python is not installed, install it as above and run `setup.bat` again.
3. **With Docker Desktop (option A):** start Docker Desktop, wait for **Engine running**, then double-click
   **`start-demo.bat`**. The first run downloads MySQL 8.4 (a few minutes).
4. **Without Docker (option C):** just double-click **`start-demo.bat`**. It says MySQL is not
   available and starts with SQLite.
5. The browser opens http://127.0.0.1:8000. From here, follow **the presentation** in Part A.

### B3. Option B: use their own MySQL server

1. Ask their DBA to run this on the MySQL server, with a password of their choice:
   ```sql
   CREATE DATABASE bc_sync CHARACTER SET utf8mb4;
   CREATE USER 'bcsync'@'%' IDENTIFIED BY 'choose-a-strong-password';
   GRANT ALL PRIVILEGES ON bc_sync.* TO 'bcsync'@'%';
   ```
2. Open `.env` in Notepad and set `MYSQL_HOST`, `MYSQL_PORT` (usually 3306), `MYSQL_DB=bc_sync`,
   `MYSQL_USER=bcsync` and `MYSQL_PASSWORD`.
3. Start with this command instead of `start-demo.bat`, because that file uses Docker:
   ```powershell
   .venv\Scripts\python run_demo.py
   ```

### B4. Later: connect his real Business Central

Use a **sandbox environment** first, never production, for the first run.

1. His Microsoft admin: in **Microsoft Entra admin center → App registrations → New
   registration**, note the **tenant id** and **client id**, and create a **client secret**.
2. Under **API permissions**: **Dynamics 365 Business Central → Application permissions →
   API.ReadWrite.All**, then **Grant admin consent**.
3. In Business Central, open the **Microsoft Entra Applications** page, add the client id, set it to
   **Enabled**, and give it permission sets for customers, vendors, items and sales orders.
4. In `.env`, set:
   ```
   BC_AUTH_MODE=entra
   BC_BASE_URL=https://api.businesscentral.dynamics.com
   BC_TENANT_ID=<tenant id>
   BC_ENVIRONMENT=<sandbox name>
   BC_CLIENT_ID=<client id>
   BC_CLIENT_SECRET=<secret>
   ```
5. Test the sign-in: `.venv\Scripts\python -m bcsync check` lists his companies.
6. Run `.venv\Scripts\python run_demo.py`. The console shows **Live tenant**. The demo-only steps (2, 5 and 6) disappear, because every change is real from here on.

---

## If something goes wrong

| What you see | Fix |
| --- | --- |
| `Docker Desktop is not running` | Start Docker Desktop, wait for **Engine running**, run `start-demo.bat` again |
| `Port 8000 is already in use` / `8765` | Another Pretech Connect window is open: close it. Or run `.venv\Scripts\python run_demo.py --port 8010` |
| Red dot next to MySQL | Docker stopped: start it, then close and reopen `start-demo.bat` |
| Step 2 says "Pull first (step 1)" | Click **Full pull now** first |
| A bc_outbox row shows **Failed** | Read *Last error* (BC's own message), fix the value, click **Retry** |
| The browser didn't open | Open http://127.0.0.1:8000 yourself |
| Fonts look plain | No internet for Google Fonts; everything still works |
