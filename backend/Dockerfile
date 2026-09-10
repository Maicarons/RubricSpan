# syntax=docker/dockerfile:1
# RubricSpan 在线服务镜像（CPU 档）。GPU（CUDA EP）需在宿主侧配置
# NVIDIA Container Toolkit 并将下方 base 换为带 CUDA/cuDNN 运行库的基础镜像。
FROM rust:1.96-slim AS build
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY crates ./crates
RUN cargo build --release -p rubricspan-server

FROM debian:bookworm-slim AS runtime
# CA 证书：OCR 模型首次启动需从 ModelScope 下载（TLS）
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /src/target/release/rubricspan-server /app/rubricspan-server
# 数据、模型、管理后台静态站均为外部挂载（见 deploy/docker-compose.yml）
VOLUME ["/app/data", "/app/models", "/app/admin"]
EXPOSE 8080
# 存储/连接串由环境变量驱动：RUBRICSPAN_STORAGE（sqlite|mysql|memory）、
# --storage 缺省回落 RUBRICSPAN_STORAGE → sqlite；mysql 用 DATABASE_URL 或 RUBRICSPAN_DB_URL。
ENTRYPOINT ["/app/rubricspan-server"]
CMD ["--listen", "0.0.0.0:8080", "--models-dir", "/app/models", "--admin-dir", "/app/admin"]
