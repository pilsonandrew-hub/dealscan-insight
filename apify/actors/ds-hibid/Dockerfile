# HiBid uses Angular SPA — requires Playwright with Chromium
FROM apify/actor-node-playwright-chrome:20

# Use the pre-installed browsers from the base image
ENV PLAYWRIGHT_BROWSERS_PATH=/pw-browsers

COPY package*.json ./
RUN npm install --include=dev

COPY . ./

CMD npm start
