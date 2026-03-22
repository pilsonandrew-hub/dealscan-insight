FROM apify/actor-node:20

COPY package*.json ./
RUN npm --quiet set progress=false && npm install --only=prod --no-audit

COPY . ./

CMD node src/main.js
