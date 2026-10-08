# Frontend dev server (Vite) on port 5173
# Run through docker compose with the backend and Piston

FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

CMD ["npm", "run", "dev", "--", "--host"]
