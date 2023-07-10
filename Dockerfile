FROM ubuntu:22.04 AS base

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Europe/Moscow

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y \
    software-properties-common \
    curl

FROM base AS deps
RUN add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y \
	nodejs \
    python3.11 \
    python3.11-dev \
    python3.11-gdbm \
    python3.11-venv
RUN curl -sSL https://bootstrap.pypa.io/get-pip.py | python3.11

FROM deps AS final
WORKDIR /app
COPY . .

RUN python3.11 setup.py
CMD python3.11 main.py