import axios from "axios";

export const PRODUCTION_API_URL = "https://real-estate-chatbot-pwjs.onrender.com";

const API_BASE = (
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? PRODUCTION_API_URL : "")
).replace(/\/$/, "");

export async function sendChat(message) {
  const { data } = await axios.post(`${API_BASE}/api/chat`, { message }, { timeout: 120000 });
  return data;
}
