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

CMD ["/usr/sbin/vsftpd", "/etc/vsftpd.conf"]
