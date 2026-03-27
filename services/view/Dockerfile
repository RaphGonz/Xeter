FROM node:20-alpine

WORKDIR /app

EXPOSE 3000

# Phase 1 stub: serve a static index.html via a simple HTTP server.
# Next.js application is scaffolded in a later phase.
RUN npm install -g serve

CMD ["serve", "-s", ".", "-l", "3000"]
