FROM apify/actor-node:20

COPY package*.json ./
RUN npm install --include=dev --quiet

COPY . ./

CMD npm start
