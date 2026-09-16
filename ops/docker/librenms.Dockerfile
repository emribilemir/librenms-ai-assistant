ARG LIBRENMS_IMAGE=librenms/librenms:latest

FROM node:22-alpine AS ui-build
WORKDIR /build
COPY chat-ui/package.json chat-ui/package-lock.json ./
RUN npm ci
COPY chat-ui/ ./
RUN npm run build \
    && mkdir -p /out \
    && cp "$(find dist/assets -maxdepth 1 -type f -name 'index-*.js' -print -quit)" /out/ai-assistant.js \
    && cp "$(find dist/assets -maxdepth 1 -type f -name 'index-*.css' -print -quit)" /out/ai-assistant.css

FROM ${LIBRENMS_IMAGE}
USER root
RUN install -d -m 0755 \
      /opt/librenms/app/Plugins/AiAssistant/resources/views \
      /opt/librenms/html/plugins/ai-assistant
COPY integrations/librenms/AiAssistant/Menu.php /opt/librenms/app/Plugins/AiAssistant/Menu.php
COPY integrations/librenms/AiAssistant/Page.php /opt/librenms/app/Plugins/AiAssistant/Page.php
COPY integrations/librenms/AiAssistant/Settings.php /opt/librenms/app/Plugins/AiAssistant/Settings.php
COPY integrations/librenms/AiAssistant/resources/views/ /opt/librenms/app/Plugins/AiAssistant/resources/views/
COPY --from=ui-build /out/ /opt/librenms/html/plugins/ai-assistant/
