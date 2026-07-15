import { useState, FormEvent } from "react";
import { TravelStyle } from "../types";
import { 
  motion 
} from "motion/react";
import { 
  Search, 
  MapPin, 
  Compass, 
  History, 
  Sparkles, 
  Calendar, 
  ChevronRight,
  Flame,
  Utensils,
  BookOpen,
  TreePine,
  DollarSign,
  Map,
  Smile
} from "lucide-react";

interface HomeDashboardProps {
  onSearchCity: (city: string, style: TravelStyle, days: number) => void;
  isLoading: boolean;
  searchHistory: { city: string; style: TravelStyle; days: number; date: string }[];
  onClearHistory: () => void;
}

const FEATURED_CITIES = [
  { name: "Kyoto", country: "Japan", style: "Historic" as TravelStyle, days: 3, emoji: "🏮", bg: "from-rose-500 to-orange-500" },
  { name: "Paris", country: "France", style: "Foodie" as TravelStyle, days: 4, emoji: "🗼", bg: "from-blue-500 to-indigo-500" },
  { name: "Reykjavik", country: "Iceland", style: "Nature" as TravelStyle, days: 3, emoji: "🏔️", bg: "from-teal-500 to-cyan-500" },
  { name: "Cairo", country: "Egypt", style: "Historic" as TravelStyle, days: 3, emoji: "🐪", bg: "from-amber-500 to-yellow-600" }
];

const STYLE_CARDS: { style: TravelStyle; label: string; desc: string; icon: any; color: string }[] = [
  { style: "Balanced", label: "Balanced Explorer", desc: "Best mix of history, food, nature, and icons", icon: Compass, color: "text-indigo-600 bg-indigo-50 border-indigo-100" },
  { style: "Foodie", label: "Culinary Connoisseur", desc: "Focuses on local delicacies, markets, and street treats", icon: Utensils, color: "text-emerald-600 bg-emerald-50 border-emerald-100" },
  { style: "Historic", label: "Heritage Historian", desc: "Museums, temples, architectural gems, and ancient routes", icon: BookOpen, color: "text-amber-600 bg-amber-50 border-amber-100" },
  { style: "Nature", label: "Wilderness Wanderer", desc: "Parks, hikes, panoramic views, and scenic lookouts", icon: TreePine, color: "text-teal-600 bg-teal-50 border-teal-100" },
  { style: "Budget", label: "Thrifty Backpacker", desc: "Free tours, budget dining, and affordable experiences", icon: DollarSign, color: "text-cyan-600 bg-cyan-50 border-cyan-100" },
  { style: "Adventure", label: "Adrenaline Seeker", desc: "Active spots, biking trails, fast-paced itineraries", icon: Flame, color: "text-orange-600 bg-orange-50 border-orange-100" }
];

export default function HomeDashboard({
  onSearchCity,
  isLoading,
  searchHistory,
  onClearHistory
}: HomeDashboardProps) {
  const [cityInput, setCityInput] = useState("");
  const [duration, setDuration] = useState<number>(3);
  const [selectedStyle, setSelectedStyle] = useState<TravelStyle>("Balanced");
  const [geoLocating, setGeoLocating] = useState(false);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!cityInput.trim() || isLoading) return;
    onSearchCity(cityInput.trim(), selectedStyle, duration);
  };

  const handleQuickCity = (city: string, style: TravelStyle, days: number) => {
    onSearchCity(city, style, days);
  };

  const handleGeolocation = () => {
    if (!navigator.geolocation) {
      alert("Geolocation is not supported by your browser");
      return;
    }

    setGeoLocating(true);
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const { latitude, longitude } = position.coords;
          // Reverse-geocoding simulation or direct lookup
          // Let's call open street maps reverse geocoding (completely free, no API key required!)
          const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}&zoom=10`);
          const data = await res.json();
          const city = data.address?.city || data.address?.town || data.address?.village || data.address?.state || "New York";
          
          setCityInput(city);
          setGeoLocating(false);
        } catch (err) {
          console.error("Reverse geocode error:", err);
          // fallback
          setCityInput("Kyoto");
          setGeoLocating(false);
        }
      },
      (error) => {
        console.error("Geolocation error:", error);
        alert("Failed to read your location. Defaulting input.");
        setGeoLocating(false);
      },
      { timeout: 8000 }
    );
  };

  return (
    <div className="w-full h-full bg-slate-50 overflow-y-auto px-4 py-5 flex flex-col gap-6 pb-24" id="home-dashboard-container">
      {/* Brand Branding Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-2xl bg-indigo-600 flex items-center justify-center text-white shadow-md">
          <Compass size={22} className="animate-pulse" />
        </div>
        <div>
          <h1 className="text-base font-bold text-slate-800 flex items-center gap-1.5">
            City Explorer <span className="text-[10px] bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded-full font-bold">PROTOTYPE</span>
          </h1>
          <p className="text-[10px] text-slate-500">Android companion for custom AI travels</p>
        </div>
      </div>

      {/* Main Search Form */}
      <div className="bg-white p-4.5 rounded-3xl shadow-sm border border-slate-100 flex flex-col gap-4">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold text-slate-700">Where are we going?</label>
            <div className="flex items-center gap-2 bg-slate-50 rounded-2xl border border-slate-100 px-3.5 py-3 transition-all focus-within:bg-white focus-within:ring-1 focus-within:ring-indigo-500">
              <Search className="text-slate-400" size={16} />
              <input
                type="text"
                value={cityInput}
                onChange={(e) => setCityInput(e.target.value)}
                placeholder="Enter any city name (e.g. Rome, Tokyo)"
                className="bg-transparent border-none outline-none text-xs flex-1 text-slate-800"
                disabled={isLoading}
              />
              <button
                type="button"
                onClick={handleGeolocation}
                disabled={isLoading || geoLocating}
                className={`p-1.5 rounded-xl transition-all ${
                  geoLocating 
                    ? "bg-indigo-100 text-indigo-600 animate-spin" 
                    : "text-slate-400 hover:text-indigo-600 hover:bg-indigo-50"
                }`}
                title="Use Current Location"
              >
                <MapPin size={15} />
              </button>
            </div>
          </div>

          {/* Stay Duration slider/selector */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center text-xs font-bold">
              <span className="text-slate-700">Stay Duration</span>
              <span className="text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-md text-[11px]">
                {duration} {duration === 1 ? "Day" : "Days"}
              </span>
            </div>
            
            <div className="flex items-center gap-4 bg-slate-50 p-3 rounded-2xl border border-slate-100">
              <Calendar size={15} className="text-slate-400 shrink-0" />
              <input
                type="range"
                min="1"
                max="5"
                value={duration}
                onChange={(e) => setDuration(parseInt(e.target.value))}
                className="w-full h-1 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-indigo-600"
                disabled={isLoading}
              />
              <span className="text-xs font-bold text-slate-500 w-5 shrink-0 text-center">5d</span>
            </div>
          </div>

          {/* Explorer Style Grid Selection */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-bold text-slate-700">Your Explorer Style</label>
            <div className="grid grid-cols-2 gap-2">
              {STYLE_CARDS.map((item) => {
                const Icon = item.icon;
                const isSelected = selectedStyle === item.style;
                return (
                  <div
                    key={item.style}
                    onClick={() => !isLoading && setSelectedStyle(item.style)}
                    className={`p-2.5 rounded-2xl border cursor-pointer transition-all flex flex-col gap-1 ${
                      isSelected
                        ? "border-indigo-600 bg-indigo-50/70 text-indigo-950 shadow-sm"
                        : "border-slate-100 bg-white text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <span className={`p-1 rounded-lg ${isSelected ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-500"}`}>
                        <Icon size={12} />
                      </span>
                      <span className="text-[10px] font-bold leading-tight truncate">{item.style}</span>
                    </div>
                    <span className="text-[8px] text-slate-400 leading-tight">
                      {item.desc}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          <button
            type="submit"
            disabled={!cityInput.trim() || isLoading}
            className={`w-full py-3.5 rounded-2xl font-semibold text-xs text-center flex items-center justify-center gap-2 transition-all shadow ${
              cityInput.trim() && !isLoading
                ? "bg-indigo-600 hover:bg-indigo-700 text-white"
                : "bg-slate-200 text-slate-400 cursor-not-allowed shadow-none"
            }`}
          >
            {isLoading ? (
              <>
                <div className="w-4 h-4 border-2 border-slate-400 border-t-white rounded-full animate-spin" />
                Generating Guide via Gemini AI...
              </>
            ) : (
              <>
                <Sparkles size={14} /> Explore This City
              </>
            )}
          </button>
        </form>
      </div>

      {/* Popular Featured Cities */}
      <div className="flex flex-col gap-2.5">
        <h3 className="text-xs font-bold text-slate-700 flex items-center gap-1">
          💡 Popular Destinations
        </h3>
        
        <div className="grid grid-cols-2 gap-2">
          {FEATURED_CITIES.map((c) => (
            <div
              key={c.name}
              onClick={() => !isLoading && handleQuickCity(c.name, c.style, c.days)}
              className="group cursor-pointer relative rounded-2xl overflow-hidden shadow-sm h-20 flex flex-col justify-end p-3 transition-transform hover:scale-[1.02]"
            >
              <div className={`absolute inset-0 bg-gradient-to-br ${c.bg} opacity-90 transition-opacity group-hover:opacity-100`} />
              <div className="relative z-10">
                <span className="text-lg block mb-1">{c.emoji}</span>
                <h4 className="text-xs font-bold text-white leading-none">{c.name}</h4>
                <span className="text-[8px] text-white/85 font-medium leading-tight mt-0.5 block">{c.days} days • {c.style}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Exploration History */}
      {searchHistory.length > 0 && (
        <div className="flex flex-col gap-2.5">
          <div className="flex justify-between items-center">
            <h3 className="text-xs font-bold text-slate-700 flex items-center gap-1">
              <History size={13} className="text-slate-500" /> Recent Explorations
            </h3>
            <button
              onClick={onClearHistory}
              className="text-[9px] font-semibold text-red-500 hover:text-red-700"
            >
              Clear
            </button>
          </div>

          <div className="flex flex-col gap-1.5">
            {searchHistory.map((h, idx) => (
              <div
                key={idx}
                onClick={() => !isLoading && onSearchCity(h.city, h.style, h.days)}
                className="bg-white p-3 rounded-2xl border border-slate-100 flex items-center justify-between cursor-pointer hover:bg-slate-50 transition-colors"
              >
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 bg-indigo-50 text-indigo-600 rounded-lg flex items-center justify-center shrink-0">
                    <Map size={14} />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-slate-800 leading-tight">{h.city}</h4>
                    <span className="text-[9px] text-slate-400">{h.days}d • {h.style} profile</span>
                  </div>
                </div>
                <ChevronRight size={14} className="text-slate-400" />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
