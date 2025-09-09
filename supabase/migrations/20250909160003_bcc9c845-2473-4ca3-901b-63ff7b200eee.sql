-- Insert missing auction sites that were added to the scraping funnel
INSERT INTO scraper_sites (id, name, base_url, category, enabled, status, priority) VALUES
-- Recently added federal/auction house sites
('bidspotter', 'BidSpotter', 'https://www.bidspotter.com', 'auction_house', true, 'active', 5),
('purplewave', 'PurpleWave', 'https://www.purplewave.com', 'auction_house', true, 'active', 5),
('jjkane', 'JJ Kane', 'https://www.jjkane.com', 'auction_house', true, 'active', 5),

-- New state surplus sites
('texas_surplus', 'Texas State Surplus', 'https://txdmv.gov', 'state', true, 'active', 5),
('arizona_surplus', 'Arizona State Surplus', 'https://azsurplus.gov', 'state', true, 'active', 5),
('colorado_surplus', 'Colorado State Surplus', 'https://colorado.gov', 'state', true, 'active', 5),
('nevada_surplus', 'Nevada State Surplus', 'https://purchasing.nv.gov', 'state', true, 'active', 5),
('new_mexico_surplus', 'New Mexico State Surplus', 'https://generalservices.state.nm.us', 'state', true, 'active', 5),

-- Municipal site
('bid4assets', 'Bid4Assets', 'https://bid4assets.com', 'municipal', true, 'active', 5),

-- Other federal sites that may be missing
('irs_auctions', 'IRS Auctions', 'https://treasury.gov', 'federal', true, 'active', 5),
('oregon_das', 'Oregon DAS', 'https://oregon.gov', 'state', true, 'active', 5),
('nc_doa', 'North Carolina DOA', 'https://ncadmin.nc.gov', 'state', true, 'active', 5)

ON CONFLICT (id) DO NOTHING;