FROM node:20-alpine

# Build-time only — ARG, not ENV, so the proxy is never present in the
# running container (the dev server and its Vite proxy talk to the `api`
# compose service by name, which a corporate proxy can't resolve).
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
