import socket
import random
import os
import csv
import time
import subprocess
from datetime import datetime

# Output directories
MUTATION_DIR = "mutated_inputs"
LOG_FILE = "fuzz_log.txt"
CSV_LOG_FILE = "fuzz_results.csv"
RESTART_LOG = "restart_log.txt"

# Create directories
os.makedirs(MUTATION_DIR, exist_ok=True)

# FTP target
TARGET_HOST = "127.0.0.1"
TARGET_PORT = 21
TIMEOUT = 5

# Docker container name
DOCKER_CONTAINER_NAME = "autofuzz-ftp-container"

# FSM-based base sequence (example for FTP)
BASE_SEQUENCE = ["USER vulnftp", "PASS 1234", "PWD", "TYPE A", "LIST", "QUIT"]

# Aggressive mutation strategies
BAD_CHARS = [chr(i) for i in list(range(0, 32)) + list(range(127, 256))]
def mutate_command(cmd):
    mutation_types = [
        lambda x: x + "A" * 10000,
        lambda x: x + "\x00" * 1000,
        lambda x: x + "../../" * 500,
        lambda x: x + "'" * 1000 + "; rm -rf / --no-preserve-root",
        lambda x: x + ''.join(random.choices(BAD_CHARS, k=2048)),
        lambda x: x.upper() * 100,
        lambda x: (x[::-1] + x[::-1]) * 50,
        lambda x: f"\xff\xfe{x}" * 100,
        lambda x: x + "\xDE\xAD\xBE\xEF" * 500,
        lambda x: "%%s%%x%%n%%p" * 1000,
        lambda x: x + ''.join(chr(random.randint(1, 255)) for _ in range(2048)),
        lambda x: x.replace("USER", "") + ''.join(random.choices(BAD_CHARS, k=1024)),
        lambda x: x + "CRASHME_NOW" * 300,
        lambda x: x + "\n" * 1000 + "\xFF" * 1000,
        lambda x: "USER root\r\nPASS toor\r\n" * 500,
        lambda x: f"{x} || echo hacked ||" + ''.join(random.choices(BAD_CHARS, k=1000)),
        lambda x: "A" * 50000,
        lambda x: "\r\n".join([x] * 100),
    ]
    return random.choice(mutation_types)(cmd)

# Logging
results = []
def log_result(test_id, cmd, response, status):
    timestamp = datetime.now().isoformat()
    results.append([test_id, timestamp, cmd, status, response[:100]])
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"[{test_id}] {cmd}\n-> {status}: {response}\n\n")

# Check if FTP is running
def is_ftp_alive():
    try:
        s = socket.socket()
        s.settimeout(3)
        s.connect((TARGET_HOST, TARGET_PORT))
        banner = s.recv(1024)
        s.close()
        return True
    except:
        return False

# Restart Docker container and count restarts
restart_counter = 0
def restart_docker():
    global restart_counter
    subprocess.run(["docker", "restart", DOCKER_CONTAINER_NAME], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    restart_counter += 1
    with open(RESTART_LOG, 'a') as f:
        f.write(f"[{datetime.now().isoformat()}] Restart #{restart_counter}\n")
    time.sleep(5)  # Give it time to restart

# Main fuzzer loop
def fuzz():
    crash_count = 0
    attempt = 0
    total = 1000

    for i in range(total):
        if not is_ftp_alive():
            log_result(i, "", "Server down. Restarting...", "RESTART")
            restart_docker()

        attempt += 1
        sequence = [mutate_command(random.choice(BASE_SEQUENCE))] + [mutate_command(cmd) for cmd in BASE_SEQUENCE]

        filename = os.path.join(MUTATION_DIR, f"testcase_{i}.txt")
        with open(filename, 'w', encoding='latin1') as f:
            f.write("\n".join(sequence))

        try:
            s = socket.socket()
            s.settimeout(TIMEOUT)
            s.connect((TARGET_HOST, TARGET_PORT))
            s.recv(1024)

            for cmd in sequence:
                s.send((cmd + "\r\n").encode('latin1'))
                response = s.recv(1024).decode('latin1', errors='ignore')
                log_result(i, cmd, response, "OK")

            s.close()

        except Exception as e:
            crash_count += 1
            log_result(i, sequence[0], str(e), "CRASH")

    return attempt, crash_count

# Save CSV summary
def export_csv():
    with open(CSV_LOG_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Test ID", "Timestamp", "Command", "Status", "Response"])
        writer.writerows(results)

# Terminal summary
def summary_report(total, crashes):
    print("\n--- AutoFuzz Summary ---")
    print(f"Total Attempts: {total}")
    print(f"Crashes Found: {crashes}")
    print(f"Container Restarts: {restart_counter}")
    print(f"Mutation Files: {MUTATION_DIR}/testcase_*.txt")
    print(f"Log File: {LOG_FILE}")
    print(f"CSV Log: {CSV_LOG_FILE}")
    print(f"Restart Log: {RESTART_LOG}\n")

if __name__ == "__main__":
    print(r"""
            Fuzzer by-:
            ____  ____  ____  ____ 
            ||S ||||J ||||A ||||K ||
            ||__||||__||||__||||__||
            |/__\||/__\||/__\||/__\|""")
    total_attempts, total_crashes = fuzz()
    export_csv()
    summary_report(total_attempts, total_crashes)