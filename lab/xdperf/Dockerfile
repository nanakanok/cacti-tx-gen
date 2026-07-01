FROM golang:trixie AS builder

RUN apt-get update && apt-get install -y \
    clang llvm libbpf-dev libc6-dev-i386 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone https://github.com/takehaya/xdperf.git .

# Patch: add XDPGenericMode fallback (same pattern as probe/xdp.go attachXDPWithFallback)
COPY xdp-generic-fallback.sh /tmp/patch.sh
RUN chmod +x /tmp/patch.sh && /tmp/patch.sh

ENV BPF_CLANG=clang
ENV BPF_CFLAGS="-O2 -g -Wall"
RUN go generate ./...
RUN CGO_ENABLED=0 go build -o /xdperf ./cmd/xdperf

RUN mkdir -p /plugins && \
    cd plugins/simpleudp.go && \
    GOOS=wasip1 GOARCH=wasm go build -buildmode=c-shared -o /plugins/simpleudp.go.wasm .

FROM debian:trixie-slim

RUN apt-get update && apt-get install -y \
    iproute2 iputils-ping \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /xdperf /usr/local/bin/xdperf
COPY --from=builder /plugins/ /usr/local/share/xdperf/plugins/

ENTRYPOINT ["sleep", "infinity"]
