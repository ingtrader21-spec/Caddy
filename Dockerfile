FROM gcr.io/distroless/static-debian13:nonroot@sha256:1c2c046bc09ed40fad370b599a0b1ae7987f55b01e247cf27a7c27cd97e5bbc7

ARG BUILD_CREATED
ARG SOURCE_URL
ARG VCS_REF
ARG VERSION

LABEL org.opencontainers.image.created="$BUILD_CREATED" \
      org.opencontainers.image.source="$SOURCE_URL" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.title="Codestra Caddy Edge" \
      org.opencontainers.image.base.name="gcr.io/distroless/static-debian13:nonroot"

COPY --chown=65532:65532 build/caddy /usr/bin/caddy
COPY --chown=0:0 build/codestra-set-bind-capability /usr/bin/codestra-set-bind-capability
USER 0:0
RUN ["/usr/bin/codestra-set-bind-capability"]
COPY --chown=65532:65532 config/ /etc/caddy/

USER 65532:65532
ENTRYPOINT ["/usr/bin/caddy"]
CMD ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
