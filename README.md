# ATTENDANCE_APP

A Flask-based attendance management portal using **MongoDB** as the backend database.

---

## Repository Overview

This repository (`ATTENDANCE_APP`) uses **MongoDB** (via PyMongo) for all data storage.

---

## MySQL-Based Repository

After searching through all repositories under `RAGHUL-19ZOROO`, the repository that uses **MySQL** for the backend is:

### [`ATTENDANCE_SYSTEM`](https://github.com/RAGHUL-19ZOROO/ATTENDANCE_SYSTEM)

- **Backend Database:** MySQL (hosted on [TiDB Cloud](https://tidbcloud.com/) — a MySQL-compatible cloud database)
- **MySQL Driver:** `mysql-connector-python`
- **Connection:** Connects to a TiDB Cloud MySQL instance (`gateway01.ap-southeast-1.prod.aws.tidbcloud.com`)
- **Language:** Python (Flask)

Key files:
- `db.py` — sets up the MySQL connection using `mysql.connector`
- `requirements.txt` — includes `mysql-connector-python==9.5.0`

---

## Summary of Backend Databases Across Repos

| Repository | Database |
|---|---|
| [ATTENDANCE_APP](https://github.com/RAGHUL-19ZOROO/ATTENDANCE_APP) | MongoDB |
| [ATTENDANCE_SYSTEM](https://github.com/RAGHUL-19ZOROO/ATTENDANCE_SYSTEM) | **MySQL** (TiDB Cloud) |
| [CANTEEN_APP](https://github.com/RAGHUL-19ZOROO/CANTEEN_APP) | — (empty repo) |
| [SMART_ATTENDANCE](https://github.com/RAGHUL-19ZOROO/SMART_ATTENDANCE) | — (empty repo) |
| [NEW-BIE](https://github.com/RAGHUL-19ZOROO/NEW-BIE) | HTML/static only |
| [COLLEGE-WEB-DESIGN](https://github.com/RAGHUL-19ZOROO/COLLEGE-WEB-DESIGN) | HTML/static only |
