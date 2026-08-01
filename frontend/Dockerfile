FROM node:20-alpine

WORKDIR /app

# Copy dependency manifests first for better layer caching
COPY package.json package-lock.json* ./
RUN npm install

# Copy the rest of the app (mounted as volume in dev, but needed for prod builds)
COPY . .

# Expose the Vite dev server port
EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
