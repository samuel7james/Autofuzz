FROM ubuntu:20.04

RUN apt-get update && apt-get install -y \
    vsftpd \
    inetutils-inetd \
    netcat \
    iputils-ping \
    tcpdump && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN useradd -m vulnftp && echo "vulnftp:1234" | chpasswd

RUN mkdir -p /var/run/vsftpd/empty /var/log/vsftpd

COPY vsftpd.conf /etc/vsftpd.conf

EXPOSE 21 30000-30009

# nosemgrep: dockerfile.security.missing-user.missing-user
# vsftpd's own architecture requires this: its master process must start
# as root to bind port 21 (a privileged port), then drops privileges
# per-connection via setuid to an unprivileged user for the actual
# FTP-session handling - the part this fuzzer targets. That's vsftpd's
# standard, secure-by-design deployment model upstream, not a gap
# introduced here; forcing a non-root Docker USER for this CMD would just
# break vsftpd's ability to bind the port. This is also an intentionally
# vulnerable, disposable, local-only fuzzing target, not a production
# image - the security bar here is "safe to run in a local Docker lab,"
# not "hardened for production."
CMD ["/usr/sbin/vsftpd", "/etc/vsftpd.conf"]
