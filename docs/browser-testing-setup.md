# Browser Testing Setup Guide

This app is built to work in a browser. You do not need the Insta360 app to test the basic flow. The same app can be opened on a PC browser and on the Insta360 ONE X2 browser as long as both devices are on the same Wi‑Fi.

## 1) Install Python

Make sure Python 3.11 or newer is installed on your PC.

- Open PowerShell.
- Run:

```powershell
py -3 --version
```

If it shows a version number, Python is ready.

## 2) Open the project folder

Open PowerShell in the project folder:

```powershell
cd C:\Users\kofor\God_Help_Business
```

## 3) Create a virtual environment

Run:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

You should see the prompt change to start with `(.venv)`.

## 4) Install the app requirements

Run:

```powershell
py -3 -m pip install -r requirements.txt
```

This installs FastAPI, SQLAlchemy, pytest, and the libraries the app needs.

## 5) Start the app

Run:

```powershell
cmd /c "cd /d C:\Users\kofor\God_Help_Business && set PYTHONPATH=. && py -3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
```

If it starts successfully, you should see a message like:

```text
Uvicorn running on http://0.0.0.0:8000
```

Leave this window open while you test.

## 6) Open it on the PC browser

In the PC browser, go to:

```text
http://127.0.0.1:8000/index.html
```

This is the main app page.

## 7) Open it on the Insta360 ONE X2 browser

On the ONE X2, connect it to the same Wi‑Fi as the PC.

Then find your PC's local IP address:

```powershell
ipconfig
```

Look for something like:

```text
IPv4 Address . . . . . . . . : 192.168.1.20
```

Now open the ONE X2 browser and go to:

```text
http://192.168.1.20:8000/index.html
```

Replace `192.168.1.20` with your real IP address.

## 8) What to test

Try these steps:

1. Open the app page.
2. Create a project.
3. Add a sample pin.
4. Open the capture map page.
5. Add a location and heading.
6. Upload a photo or native Insta360 file if you have one.
7. Open the review page.
8. Create a share link.

## 9) If it does not load

Check these things:

- The Python app is still running.
- Both devices are on the same Wi‑Fi.
- You used the correct PC IP address.
- Port 8000 is not blocked.
- You opened the URL with `http://` not `https://`.

## 10) Easy summary

If you want the short version:

1. Install Python.
2. Open the project folder.
3. Create `.venv` and activate it.
4. Run `pip install -r requirements.txt`.
5. Start Uvicorn on port 8000.
6. Open `http://127.0.0.1:8000/index.html` on the PC.
7. Open `http://<PC-IP>:8000/index.html` on the ONE X2.

This is the browser-first test route for this app.
