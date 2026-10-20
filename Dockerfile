FROM ghcr.io/prefix-dev/pixi:latest

# Fix the missing libGL.so.1 issue Badger (Qt) hits on a headless base image.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /playground
COPY pixi.toml pixi.lock ./
RUN pixi install --locked

COPY . .
RUN pixi run setup -- --yes

ENTRYPOINT ["pixi", "run", "badger"]
