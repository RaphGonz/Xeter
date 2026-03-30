FROM node:20-alpine

WORKDIR /app

COPY services/view/package*.json ./
RUN npm install

COPY services/view/ .

EXPOSE 3000

CMD ["npm", "run", "dev"]
