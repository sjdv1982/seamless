FROM debian:latest

RUN apt-get update && apt-get install -y cowsay && cp /usr/games/cowsay /usr/bin
