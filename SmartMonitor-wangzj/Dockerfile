FROM maven:3.8.8-eclipse-temurin-8 AS build

WORKDIR /workspace
COPY . .
RUN mvn clean package -DskipTests

FROM eclipse-temurin:8-jre

ENV TZ=Asia/Shanghai
WORKDIR /app

RUN mkdir -p /app/uploadPath

COPY --from=build /workspace/hxjm-admin/target/hxjm-admin.jar /app/app.jar

EXPOSE 18080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
