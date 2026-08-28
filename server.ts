import express from "express";
import http from "http";
import path from "path";
import { createServer as createViteServer } from "vite";
import { GoogleGenAI, Type } from "@google/genai";
import dotenv from "dotenv";

dotenv.config();

const app = express();
const PORT = 3000;

app.use(express.json({ limit: "5mb" }));

// Lazy initializer for Gemini Client
let aiClient: GoogleGenAI | null = null;
function getGeminiClient() {
  if (!aiClient) {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      throw new Error("GEMINI_API_KEY environment variable is required");
    }
    aiClient = new GoogleGenAI({
      apiKey,
      httpOptions: {
        headers: {
          "User-Agent": "aistudio-build",
        },
      },
    });
  }
  return aiClient;
}

// 1. Explore City Endpoint - Structured Guide & Itinerary
app.post("/api/explore", async (req, res) => {
  try {
    const { city, travelStyle = "Balanced", duration = 3 } = req.body;
    if (!city || typeof city !== "string") {
      return res.status(400).json({ error: "City name is required" });
    }

    const ai = getGeminiClient();
    const prompt = `Generate a highly detailed, immersive travel guide and a day-by-day itinerary for exploring the city of "${city}".
The traveler's style is "${travelStyle}" and the stay duration is ${duration} days.
Make sure all coordinates (latOffset and lngOffset) are balanced numbers between -80 and 80 representing visual positions on a relative coordinate grid for a custom interactive map.
Ensure you return exactly the matching JSON schema requested, containing landmarks, dining, parks, and secret spots.`;

    const systemInstruction = `You are a native expert local guide for any city in the world.
Your job is to provide factual, highly specific local secrets, exact places to eat, iconic landmarks, and a customized day-by-day track.
Avoid generic descriptions. Name actual, real, famous or hidden places in the city.
When producing coordinates (latOffset, lngOffset), ensure they are reasonably spread out across the visual canvas (e.g. one landmark at -40, 30, a restaurant at 20, -50) to create an interesting and beautiful map layout.`;

    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash",
      contents: prompt,
      config: {
        systemInstruction,
        temperature: 0.7,
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.OBJECT,
          required: [
            "cityName",
            "country",
            "description",
            "bestTimeToVisit",
            "weatherSummary",
            "localCurrency",
            "localGreeting",
            "etiquetteTips",
            "survivalPhrases",
            "spots",
            "itinerary"
          ],
          properties: {
            cityName: { type: Type.STRING, description: "The normalized name of the city, e.g. Kyoto" },
            country: { type: Type.STRING, description: "The country where the city is located, e.g. Japan" },
            description: { type: Type.STRING, description: "A beautiful, evocative 2-3 sentence description of the city's vibe." },
            bestTimeToVisit: { type: Type.STRING, description: "Best months to visit and why." },
            weatherSummary: { type: Type.STRING, description: "Current season climate/packing advice." },
            localCurrency: { type: Type.STRING, description: "Currency name and symbol, e.g. Japanese Yen (¥)" },
            localGreeting: { type: Type.STRING, description: "Common friendly greeting, e.g. Konnichiwa" },
            etiquetteTips: {
              type: Type.ARRAY,
              items: { type: Type.STRING },
              description: "3 highly important cultural tips (e.g., tipping rules, shoes-off rules, subway etiquette)."
            },
            survivalPhrases: {
              type: Type.ARRAY,
              items: {
                type: Type.OBJECT,
                required: ["phrase", "meaning", "pronunciation"],
                properties: {
                  phrase: { type: Type.STRING, description: "The phrase in local script/language." },
                  meaning: { type: Type.STRING, description: "English meaning." },
                  pronunciation: { type: Type.STRING, description: "How to pronounce it phonetically." }
                }
              },
              description: "4 essential local survival phrases."
            },
            spots: {
              type: Type.ARRAY,
              items: {
                type: Type.OBJECT,
                required: [
                  "id",
                  "name",
                  "category",
                  "description",
                  "bestTimeOfDay",
                  "activityLevel",
                  "latOffset",
                  "lngOffset",
                  "recommendedDuration"
                ],
                properties: {
                  id: { type: Type.STRING, description: "Unique slug id, e.g. 'fushimi-inari'" },
                  name: { type: Type.STRING, description: "Full proper name of the place." },
                  category: {
                    type: Type.STRING,
                    enum: ["landmark", "food", "nature", "secret"],
                    description: "Category of the place."
                  },
                  description: { type: Type.STRING, description: "A captivating, concise sentence explaining what makes it special." },
                  bestTimeOfDay: { type: Type.STRING, enum: ["morning", "afternoon", "evening", "night"] },
                  activityLevel: { type: Type.STRING, enum: ["low", "medium", "high"] },
                  latOffset: { type: Type.NUMBER, description: "Visual coordinate offset Y on map, between -80 and 80" },
                  lngOffset: { type: Type.NUMBER, description: "Visual coordinate offset X on map, between -80 and 80" },
                  recommendedDuration: { type: Type.STRING, description: "e.g., '1-2 hours' or 'Half day'" }
                }
              },
              description: "A rich curated collection of 8-10 interesting places to visit in the city."
            },
            itinerary: {
              type: Type.ARRAY,
              items: {
                type: Type.OBJECT,
                required: ["dayNumber", "theme", "activities"],
                properties: {
                  dayNumber: { type: Type.INTEGER },
                  theme: { type: Type.STRING, description: "Daily theme, e.g. 'Historic Temples & Zen Gardens'" },
                  activities: {
                    type: Type.ARRAY,
                    items: {
                      type: Type.OBJECT,
                      required: ["time", "spotName", "activityDescription", "spotId"],
                      properties: {
                        time: { type: Type.STRING, description: "e.g., '09:00 AM' or '01:00 PM'" },
                        spotName: { type: Type.STRING },
                        activityDescription: { type: Type.STRING, description: "Specific advice on what to do or try here." },
                        spotId: { type: Type.STRING, description: "ID matching one of the items in 'spots'." }
                      }
                    }
                  }
                }
              },
              description: "Day-by-day timeline mapping exactly to the length requested."
            }
          }
        }
      }
    });

    const text = response.text;
    if (!text) {
      throw new Error("No response content generated from Gemini.");
    }

    const data = JSON.parse(text.trim());
    res.json(data);
  } catch (error: any) {
    console.error("Explore API Error:", error);
    res.status(500).json({ error: error.message || "Failed to generate city guide" });
  }
});

// 2. Chat / Travel Companion Endpoint
app.post("/api/chat", async (req, res) => {
  try {
    const { city, messages = [], travelStyle = "Balanced" } = req.body;
    if (!city || typeof city !== "string") {
      return res.status(400).json({ error: "City context is required" });
    }

    const ai = getGeminiClient();

    // Map client message format to Gemini's history or format
    // For a simple chat completion, we can concatenate or provide a system instruction and chat history.
    const systemInstruction = `You are an Android-based travel assistant inside the 'City Explorer' app.
You are helping a traveler currently exploring "${city}". Their travel style is "${travelStyle}".
Provide fast, helpful, bite-sized local answers. Keep answers brief (under 120 words) and format key points in clean, friendly paragraphs or short bullets.
Be highly accurate about transit, etiquette, hydration, local safety, and food recommendations. Use a warm, enthusiastic local guide tone.`;

    // Take the last 6 messages to keep context without exceeding limits
    const chatHistory = messages.slice(-6).map((m: any) => {
      return `${m.role === "user" ? "Traveler" : "Assistant"}: ${m.content}`;
    }).join("\n");

    const userMessage = messages[messages.length - 1]?.content || "Tell me a fun local trivia!";

    const prompt = `Here is our conversation history:\n${chatHistory}\n\nTraveler: ${userMessage}\nAssistant:`;

    const response = await ai.models.generateContent({
      model: "gemini-3.5-flash",
      contents: prompt,
      config: {
        systemInstruction,
        temperature: 0.7,
      }
    });

    res.json({ content: response.text?.trim() || "I'm having trouble retrieving tips right now. Let's try another topic!" });
  } catch (error: any) {
    console.error("Chat API Error:", error);
    res.status(500).json({ error: error.message || "Failed to process chat" });
  }
});

// Setup Vite Dev server or static asset server
async function startServer() {
  const httpServer = http.createServer(app);

  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: {
        middlewareMode: true,
        // Attach Vite's HMR websocket to the same HTTP server as Express.
        // Without this, the preview proxy connects to a websocket that never opens.
        hmr: { server: httpServer },
      },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  httpServer.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on port ${PORT}`);
  });
}

startServer();
