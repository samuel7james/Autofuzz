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
cd docker/
docker build -t autofuzz-ftp .
docker run -d --name autofuzz-ftp-container -p 21:21 -p 30000-30009:30000-30009 autofuzz-ftp
```

### 2. Run The Fuzzer

```bash
python3 autofuzz.py
```
---
Execute this command to start the fuzzing process. The script will mutate FTP commands, send them to the server, and track any crashes or restarts that occur. It will also log the results for further analysis.