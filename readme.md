# AutoFuzz

AutoFuzz is a CLI-based, FSM-guided fuzzing framework designed for testing FTP servers. It aggressively mutates protocol commands, detects crashes, and automatically restarts the target Docker container when faults are observed.

## ✨ Features

- Finite State Machine (FSM)-inspired input sequencing
- Aggressive mutation strategies for buffer overflow and logic fault detection
- Docker container auto-restart on crash
- Persistent logging in text and CSV formats
- CLI-based, zero GUI dependencies

## 🛠️ Requirements

- Python 3.8+
- Docker (installed and running)

## 🚀 How to Use

### 1. Set up the vulnerable FTP server

```bash
cd docker/
docker build -t autofuzz-ftp .
docker run -d --name autofuzz-ftp-container -p 21:21 -p 30000-30009:30000-30009 autofuzz-ftp