FROM caddy@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648

ARG BUILD_CREATED
ARG SOURCE_URL
ARG VCS_REF
ARG VERSION

LABEL org.opencontainers.image.created="$BUILD_CREATED" \
      org.opencontainers.image.source="$SOURCE_URL" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.title="Codestra Caddy Edge"

RUN install -d -o 65532 -g 65532 /config/caddy /data/caddy /run/caddy /var/log/caddy
COPY --chown=65532:65532 config/ /etc/caddy/

USER 65532:65532
ENTRYPOINT ["caddy"]
CMD ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
