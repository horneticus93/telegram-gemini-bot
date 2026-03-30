FROM apache/age:latest
RUN apt-get update -y \
    && apt-get install -y build-essential postgresql-server-dev-18 git \
    && cd /tmp \
    && git clone https://github.com/pgvector/pgvector.git \
    && cd pgvector \
    && make \
    && make install \
    && rm -rf /tmp/pgvector \
    && apt-get remove -y build-essential postgresql-server-dev-18 git \
    && rm -rf /var/lib/apt/lists/*
