# Multi-stage build for the Go compliance pipeline.
# Build context: repo root (needs ../data relative-path compatibility, see below).

FROM golang:1.24-alpine AS builder
WORKDIR /src/pipeline
COPY pipeline/go.mod pipeline/go.sum ./
RUN go mod download
COPY pipeline/ .
RUN CGO_ENABLED=0 go build -o /out/pipeline .

FROM alpine:3.19
RUN adduser -D -u 10001 appuser
WORKDIR /app/pipeline
COPY --from=builder /out/pipeline ./pipeline
# The current code opens "../data/loans.csv" relative to its own working
# directory (see engineering audit notes) — data/ is copied one level up
# from the binary's WORKDIR so that relative path resolves unchanged.
# TODO: replace with PostgreSQL-backed data access per
# docs/production-architecture.md before this file is no longer needed.
COPY data/ /app/data/
USER appuser
ENTRYPOINT ["./pipeline"]
