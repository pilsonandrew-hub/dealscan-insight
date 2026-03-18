FROM apify/actor-node-playwright-chrome:20

ENV PLAYWRIGHT_BROWSERS_PATH=/pw-browsers

COPY package*.json ./
RUN npm install --include=dev

COPY . ./

CMD npm start
