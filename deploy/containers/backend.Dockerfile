FROM maven:3.8.8-eclipse-temurin-8 AS development
WORKDIR /app/backend
ENV MAVEN_CONFIG=/runtime/maven
COPY SmartMonitor-wangzj ./
RUN MAVEN_OPTS="-Xmx1024m" mvn -pl hxjm-admin -am package -DskipTests -q
CMD ["mvn", "-pl", "hxjm-admin", "-am", "package", "-DskipTests"]
FROM eclipse-temurin:8u442-b06-jre-jammy AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=development /app/backend/hxjm-admin/target/hxjm-admin.jar /app/app.jar
ARG REVISION=unknown
ENV HXJM_REVISION=$REVISION HOME=/tmp
LABEL org.opencontainers.image.revision=$REVISION
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
