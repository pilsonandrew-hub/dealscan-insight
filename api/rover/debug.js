export default function handler(_req, res) {
  return res.status(404).json({ detail: 'Not found' });
}
