FROM python:3.13-slim

RUN pip install --no-cache-dir snmpsim==1.2.2 pysmi \
    && useradd --create-home --uid 10001 snmpsim
COPY ops/docker/snmpsim-entrypoint.sh /usr/local/bin/snmpsim-entrypoint
RUN chmod 0755 /usr/local/bin/snmpsim-entrypoint

USER snmpsim
ENTRYPOINT ["/usr/local/bin/snmpsim-entrypoint"]
