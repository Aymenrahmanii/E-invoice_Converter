# KoSIT validator with the XRechnung configuration, served over HTTP (daemon mode).
# POST an XML file to http://localhost:8081/ to get the report back.
FROM eclipse-temurin:21-jre
ARG KOSIT_VERSION=1.6.3
ARG XR_CONFIG_TAG=v2026-08-31
ARG XR_CONFIG_ZIP=xrechnung-3.0.2-validator-configuration-2026-08-31.zip
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/kosit
RUN curl -fsSL -o validator.jar \
      https://github.com/itplr-kosit/validator/releases/download/v${KOSIT_VERSION}/validator-${KOSIT_VERSION}-standalone.jar \
 && curl -fsSL -o config.zip \
      https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/download/${XR_CONFIG_TAG}/${XR_CONFIG_ZIP} \
 && mkdir config && unzip -q config.zip -d config && rm config.zip
EXPOSE 8080
CMD ["java", "-jar", "validator.jar", "-s", "config/scenarios.xml", "-r", "config", "-D", "-H", "0.0.0.0", "-P", "8080"]
