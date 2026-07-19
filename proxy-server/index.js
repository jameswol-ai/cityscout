// proxy-server/index.js
const express = require('express');
const axios = require('axios');
const rateLimit = require('express-rate-limit'); // optional
const Redis = require('ioredis'); // optional if using Redis caching
const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;
const GOOGLE_API_KEY = process.env.GOOGLE_API_KEY;
if (!GOOGLE_API_KEY) {
  console.error('Missing GOOGLE_API_KEY');
  process.exit(1);
}

// Optional rate limiter
const limiter = rateLimit({
  windowMs: 60 * 1000,
  max: 60
});
app.use(limiter);

// Optional Redis client (used in caching example)
const redisUrl = process.env.REDIS_URL || null;
let redis = null;
if (redisUrl) {
  redis = new Redis(redisUrl);
}

// Helper: safe fetch wrapper
async function safeGet(url, params = {}) {
  const res = await axios.get(url, { params, timeout: 10000 });
  return res.data;
}

// Places textsearch proxy
app.get('/api/places', async (req, res) => {
  try {
    const { query, city } = req.query;
    if (!query && !city) return res.status(400).json({ error: 'query or city required' });

    const q = query ? `${query} in ${city || ''}` : city;
    const cacheKey = `places:${q}`;

    if (redis) {
      const cached = await redis.get(cacheKey);
      if (cached) return res.json(JSON.parse(cached));
    }

    const url = 'https://maps.googleapis.com/maps/api/place/textsearch/json';
    const data = await safeGet(url, { query: q, key: GOOGLE_API_KEY });

    if (redis) await redis.set(cacheKey, JSON.stringify(data), 'EX', 60 * 60); // 1 hour
    res.json(data);
  } catch (err) {
    console.error(err.message);
    res.status(500).json({ error: 'Places request failed' });
  }
});

// Directions proxy
app.get('/api/directions', async (req, res) => {
  try {
    const { origin, destination } = req.query;
    if (!origin || !destination) return res.status(400).json({ error: 'origin and destination required' });

    const cacheKey = `directions:${origin}:${destination}`;
    if (redis) {
      const cached = await redis.get(cacheKey);
      if (cached) return res.json(JSON.parse(cached));
    }

    const url = 'https://maps.googleapis.com/maps/api/directions/json';
    const data = await safeGet(url, { origin, destination, key: GOOGLE_API_KEY });

    if (redis) await redis.set(cacheKey, JSON.stringify(data), 'EX', 60 * 30); // 30 minutes
    res.json(data);
  } catch (err) {
    console.error(err.message);
    res.status(500).json({ error: 'Directions request failed' });
  }
});

// Photo proxy (returns redirect to Google photo or streams bytes)
app.get('/api/photo', async (req, res) => {
  try {
    const { photoreference, maxwidth = 800 } = req.query;
    if (!photoreference) return res.status(400).json({ error: 'photoreference required' });

    const url = 'https://maps.googleapis.com/maps/api/place/photo';
    const params = { photoreference, maxwidth, key: GOOGLE_API_KEY };
    // Let axios follow redirect and stream bytes
    const response = await axios.get(url, { params, responseType: 'stream', timeout: 10000 });
    res.setHeader('Content-Type', response.headers['content-type'] || 'image/jpeg');
    response.data.pipe(res);
  } catch (err) {
    console.error(err.message);
    res.status(500).json({ error: 'Photo request failed' });
  }
});

app.listen(PORT, () => console.log(`Proxy server listening on ${PORT}`));
