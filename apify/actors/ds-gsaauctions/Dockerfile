FROM apify/actor-node:20

COPY package*.json ./
RUN npm install --include=dev

COPY . ./

CMD npm start
