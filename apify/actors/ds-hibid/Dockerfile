# HiBid uses Angular SPA — requires Playwright with Chromium
FROM apify/actor-node-playwright-chrome:20

COPY package*.json ./
RUN npm install --include=dev

# Install Playwright browser binaries matching the installed package version
RUN npx playwright install chromium

COPY . ./

CMD npm start
