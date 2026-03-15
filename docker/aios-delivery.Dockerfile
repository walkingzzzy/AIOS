FROM rust:1.85.0-bookworm

RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --fix-missing --no-install-recommends \
        ca-certificates \
        git \
        pkg-config \
        libssl-dev \
        python3 \
        python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m pip install --break-system-packages PyYAML

WORKDIR /workspace
