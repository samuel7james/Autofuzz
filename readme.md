# AutoFuzz

![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

AutoFuzz is a CLI-based, FSM-guided fuzzing framework designed for automated testing of FTP servers. It aggressively mutates protocol commands, detects crashes, and automatically restarts the target Docker container when faults are observed. This project supports academic research in network protocol security testing and fuzzing automation.

---

## ✨ Features

- ✅ FSM-based input sequencing for realistic protocol flow
- 💣 High-intensity mutation strategies targeting buffer overflows and malformed input handling
- 🔄 Auto-restart of Docker containers upon crash detection
- 📝 Persistent logs: plain text + structured CSV for research
- 🧪 Easily modifiable to test other text-based protocols

---

## 🛠️ Requirements

- Python 3.8+
- Docker (installed and running)

---

## 🚀 How to Use

### 1. Set up the vulnerable FTP server

```bash
cd docker/labs/ftp-vsftpd/
docker build -t autofuzz-ftp .
docker run -d --name autofuzz-ftp-container -p 21:21 -p 30000-30009:30000-30009 autofuzz-ftp
```

### 2. Install AutoFuzz

```bash
pip install -e .
```

### 3. Run The Fuzzer

```bash
autofuzz proto 127.0.0.1:21 --profile examples/configs/ftp-lab.yaml
```
This mutates FTP commands, sends them to the server, and classifies any
crashes or unexpected disconnects encountered along the way, printing a
findings summary when the run completes.

> **Note:** AutoFuzz v2 is under active development in `src/autofuzz/`; see
> `PROJECT_PLAN.md` and `TASKS.md` for the architecture and current status.
> The Protocol Fuzzing Engine (used above) is fully implemented; the Web
> Assessment Engine (`autofuzz web <url>`) is not yet wired up to a
> runnable scan.

---
