import { useState, useEffect } from "react";
import { CityGuide, Spot, TravelStyle, Message } from "./types";
import HomeDashboard from "./components/HomeDashboard";
import MapWidget from "./components/MapWidget";
import ItineraryTimeline from "./components/ItineraryTimeline";
import SurvivalGuide from "./components/SurvivalGuide";
import CompanionChat from "./components/CompanionChat";
import BottomNav, { TabType } from "./components/BottomNav";
import { motion, AnimatePresence } from "motion/react";
import { 
  Wifi, 
  Battery, 
  Signal, 
  Circle, 
  Square, 
  Triangle, 
  Sparkles,
  Compass,
  MapPin,
  RefreshCw,
  X,
  AlertCircle
} from "lucide-react";

export default function App() {
  const [activeTab, setActiveTab] = useState<TabType>("explore");
  const [activeCity, setActiveCity] = useState<string>("");
  const [activeStyle, setActiveStyle] = useState<TravelStyle>("Balanced");
  const [activeDays, setActiveDays] = useState<number>(3);
  
  const [cityGuide, setCityGuide] = useState<CityGuide | null>(null);
  const [selectedSpot, setSelectedSpot] = useState<Spot | null>(null);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [visitedPlaces, setVisitedPlaces] = useState<string[]>([]);
  const [activeDay, setActiveDay] = useState<number>(1);
  const [chatHistory, setChatHistory] = useState<Message[]>([]);
  const [searchHistory, setSearchHistory] = useState<{ city: string; style: TravelStyle; days: number; date: string }[]>([]);
  
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [loadingStep, setLoadingStep] = useState<number>(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  
  // Real-time clock for Android Status Bar
  const [currentTime, setCurrentTime] = useState<string>("09:41");

  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      let hours = now.getHours();
      let minutes = now.getMinutes().toString().padStart(2, "0");
      setCurrentTime(`${hours}:${minutes}`);
    };
    updateClock();
    const interval = setInterval(updateClock, 60000);
    return () => clearInterval(interval);
  }, []);

  // Load search history and state from localStorage on startup
  useEffect(() => {
    try {
      const historyStr = localStorage.getItem("city_explorer_history");
      if (historyStr) {
        setSearchHistory(JSON.parse(historyStr));
      }

      const favsStr = localStorage.getItem("city_explorer_favorites");
      if (favsStr) {
        setFavorites(JSON.parse(favsStr));
      }

      const visitedStr = localStorage.getItem("city_explorer_visited");
      if (visitedStr) {
        setVisitedPlaces(JSON.parse(visitedStr));
      }
    } catch (e) {
      console.error("Error reading localStorage", e);
    }
  }, []);

  // Sequential simulated guide steps for high reassurance during Gemini compilation
  const loadingMessages = [
    "Contacting Gemini local expert guide...",
    "Drafting day-by-day customized travel route...",
    "Curating authentic food joints & secret landmarks...",
    "Translating essential survival language phrases...",
    "Synchronizing coordinate coordinates for interactive mapping...",
    "Assembling your mobile city explorer handbook..."
  ];

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isLoading) {
      setLoadingStep(0);
      interval = setInterval(() => {
        setLoadingStep((prev) => (prev < loadingMessages.length - 1 ? prev + 1 : prev));
      }, 2500);
    }
    return () => clearInterval(interval);
  }, [isLoading]);

  // Main Action: Fetch City Exploration Guide from Backend
  const handleSearchCity = async (city: string, style: TravelStyle, days: number) => {
    setIsLoading(true);
    setErrorMsg(null);
    setSelectedSpot(null);
    setVisitedPlaces([]);

    try {
      const response = await fetch("/api/explore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ city, travelStyle: style, duration: days }),
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.error || "Failed to compile travel guide.");
      }

      const data: CityGuide = await response.json();
      setCityGuide(data);
      setActiveCity(data.cityName);
      setActiveStyle(style);
      setActiveDays(days);
      setActiveDay(1);
      setActiveTab("map"); // auto-switch to interactive map once generated!

      // Save to Search history list
      const updatedHistory = [
        { city: data.cityName, style, days, date: new Date().toLocaleDateString() },
        ...searchHistory.filter(h => h.city.toLowerCase() !== data.cityName.toLowerCase())
      ].slice(0, 5); // max 5

      setSearchHistory(updatedHistory);
      localStorage.setItem("city_explorer_history", JSON.stringify(updatedHistory));

      // Reset AI Chat for new city
      const welcomeMsg: Message = {
        role: "assistant",
        content: `Welcome to ${data.cityName}, ${data.country}! 🏮 I'm your local ${style} guide. Ask me any practical tips or secrets about your ${days}-day visit!`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      };
      setChatHistory([welcomeMsg]);

    } catch (err: any) {
      console.error(err);
      setErrorMsg(err.message || "An unexpected error occurred during exploration.");
    } finally {
      setIsLoading(false);
    }
  };

  // Clear search history
  const handleClearHistory = () => {
    setSearchHistory([]);
    localStorage.removeItem("city_explorer_history");
  };

  // Toggle favorite spots
  const handleToggleFavorite = (spotId: string) => {
    let updated: string[];
    if (favorites.includes(spotId)) {
      updated = favorites.filter(id => id !== spotId);
    } else {
      updated = [...favorites, spotId];
    }
    setFavorites(updated);
    localStorage.setItem("city_explorer_favorites", JSON.stringify(updated));
  };

  // Toggle visited checkbox in itinerary
  const handleToggleVisited = (spotId: string) => {
    let updated: string[];
    if (visitedPlaces.includes(spotId)) {
      updated = visitedPlaces.filter(id => id !== spotId);
    } else {
      updated = [...visitedPlaces, spotId];
    }
    setVisitedPlaces(updated);
    localStorage.setItem("city_explorer_visited", JSON.stringify(updated));
  };

  // Chat message submission to backend
  const handleSendChatMessage = async (text: string) => {
    if (!cityGuide) return;
    
    const userMsg: Message = {
      role: "user",
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    };

    const newHistory = [...chatHistory, userMsg];
    setChatHistory(newHistory);
    setIsLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          city: cityGuide.cityName,
          travelStyle: activeStyle,
          messages: newHistory.map(m => ({ role: m.role, content: m.content }))
        })
      });

      if (!response.ok) throw new Error("Local assistant was disconnected.");

      const data = await response.json();
      const botMsg: Message = {
        role: "assistant",
        content: data.content,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      };

      setChatHistory(prev => [...prev, botMsg]);
    } catch (e: any) {
      const errorBotMsg: Message = {
        role: "assistant",
        content: `Sorry, I'm experiencing some connectivity issues: ${e.message}. Can we try again?`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      };
      setChatHistory(prev => [...prev, errorBotMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  // Spot sequencing to connect on the map for selected day
  const activeDayRouteSpots = useEffectMemo(() => {
    if (!cityGuide) return [];
    const dayData = cityGuide.itinerary.find(day => day.dayNumber === activeDay);
    if (!dayData) return [];
    return dayData.activities
      .map(act => cityGuide.spots.find(s => s.id === act.spotId))
      .filter((s): s is Spot => !!s);
  }, [cityGuide, activeDay]);

  // Handle click on Virtual Back/Home/Recents buttons
  const handleVirtualNavigation = (action: "back" | "home" | "recents") => {
    if (action === "home" || action === "back") {
      setActiveTab("explore");
      setSelectedSpot(null);
    } else if (action === "recents") {
      // Toggle display of search panel or general overview
      if (searchHistory.length > 0) {
        alert(`Recents: You have searched for ${searchHistory.map(h => h.city).join(", ")} in the past.`);
      } else {
        alert("Recents: No past explorations found.");
      }
    }
  };

  return (
    <div className="w-full min-h-screen bg-slate-900 flex items-center justify-center p-0 md:p-6 select-none" id="android-device-frame-viewport">
      {/* Curved Premium Android Flagship Frame Mockup */}
      <div className="relative w-full h-screen md:h-[780px] md:w-[380px] bg-slate-900 md:rounded-[40px] md:shadow-2xl md:border-[10px] md:border-slate-800 flex flex-col overflow-hidden transition-all duration-300">
        
        {/* PHYSICAL POWER & VOLUME BUTTONS (Decorational accents on desktop) */}
        <div className="hidden md:block absolute right-[-12px] top-[140px] w-1.5 h-16 bg-slate-700 rounded-l-md border-r border-slate-900 z-50 hover:bg-slate-500 transition-colors cursor-pointer" title="Power Button" onClick={() => handleVirtualNavigation("home")} />
        <div className="hidden md:block absolute right-[-12px] top-[220px] w-1.5 h-12 bg-slate-700 rounded-l-md border-r border-slate-900 z-50" title="Volume Up" />
        <div className="hidden md:block absolute right-[-12px] top-[275px] w-1.5 h-12 bg-slate-700 rounded-l-md border-r border-slate-900 z-50" title="Volume Down" />

        {/* SCREEN STAGE: Matches standard mobile screens */}
        <div className="flex-1 w-full bg-white flex flex-col overflow-hidden relative">
          
          {/* ANDROID SYSTEM TOP NOTCH CAMERA & STATUS BAR */}
          <div className="bg-white/95 backdrop-blur px-5 pt-3 pb-1.5 flex items-center justify-between text-xs font-semibold text-slate-800 select-none border-b border-slate-50 z-30 shrink-0">
            {/* Live Clock Status */}
            <span className="font-bold tracking-tight text-[11px]">{currentTime}</span>

            {/* Front Camera Notch (Middle Punch-hole) */}
            <div className="absolute top-2 left-1/2 -translate-x-1/2 w-4 h-4 rounded-full bg-black border-2 border-slate-900 shadow-inner flex items-center justify-center">
              <span className="w-1 h-1 rounded-full bg-blue-900" />
            </div>

            {/* System Status Indicators */}
            <div className="flex items-center gap-1.5 text-slate-600">
              <Signal size={12} className="text-slate-800" />
              <Wifi size={12} className="text-slate-800" />
              <div className="flex items-center gap-0.5">
                <span className="text-[9px] font-bold">85%</span>
                <Battery size={13} className="text-slate-800 rotate-0" />
              </div>
            </div>
          </div>

          {/* ACTIVE SCREEN CONTENT STAGE */}
          <div className="flex-1 w-full overflow-hidden relative bg-slate-50">
            <AnimatePresence mode="wait">
              {isLoading && cityGuide === null ? (
                /* GORGEOUS ANIMATED GEMINI COMPILING STAGE */
                <motion.div
                  key="loading"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="absolute inset-0 bg-slate-900 z-50 flex flex-col items-center justify-center p-6 text-center select-none"
                >
                  <div className="relative mb-6">
                    {/* Ring ripple animations */}
                    <div className="absolute inset-[-15px] rounded-full border-2 border-indigo-500/25 animate-ping" />
                    <div className="absolute inset-[-30px] rounded-full border border-indigo-400/10 animate-[ping_4s_ease-in-out_infinite]" />
                    <div className="w-16 h-16 rounded-full bg-indigo-600 flex items-center justify-center text-white shadow-xl">
                      <Compass size={28} className="animate-[spin_4s_linear_infinite]" />
                    </div>
                  </div>

                  <h3 className="text-sm font-bold text-white tracking-wide flex items-center gap-1.5">
                    <Sparkles size={16} className="text-indigo-400 animate-pulse" /> Compiling City Guide
                  </h3>
                  <p className="text-[10px] text-slate-400 mt-1 uppercase tracking-widest font-bold">Powered by Gemini 3.5</p>

                  {/* Animated sliding progress messages */}
                  <div className="mt-8 h-12 overflow-hidden relative w-full">
                    <AnimatePresence mode="wait">
                      <motion.div
                        key={loadingStep}
                        initial={{ y: 20, opacity: 0 }}
                        animate={{ y: 0, opacity: 1 }}
                        exit={{ y: -20, opacity: 0 }}
                        className="text-xs text-indigo-300 px-4 leading-relaxed font-medium"
                      >
                        {loadingMessages[loadingStep]}
                      </motion.div>
                    </AnimatePresence>
                  </div>

                  {/* Tiny progress bars */}
                  <div className="w-40 bg-slate-800 h-1 rounded-full mt-4 overflow-hidden">
                    <motion.div 
                      className="bg-indigo-500 h-full rounded-full" 
                      animate={{ width: `${((loadingStep + 1) / loadingMessages.length) * 100}%` }}
                      transition={{ duration: 0.8 }}
                    />
                  </div>
                </motion.div>
              ) : errorMsg ? (
                /* ERROR HANDLING REASSURANCE WINDOW */
                <motion.div
                  key="error"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="absolute inset-0 bg-white z-50 flex flex-col items-center justify-center p-6 text-center"
                >
                  <div className="w-12 h-12 rounded-full bg-red-50 border border-red-200 text-red-500 flex items-center justify-center mb-4 shadow-sm">
                    <AlertCircle size={24} />
                  </div>
                  <h3 className="text-sm font-bold text-slate-800">Connection Interrupted</h3>
                  <p className="text-xs text-slate-500 mt-2 leading-relaxed px-4">
                    {errorMsg}
                  </p>
                  <button
                    onClick={() => setErrorMsg(null)}
                    className="mt-6 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold shadow"
                  >
                    Try Again
                  </button>
                </motion.div>
              ) : (
                /* PRIMARY VIEW SWAP SWITCHBOARD */
                <motion.div
                  key={activeTab}
                  initial={{ opacity: 0, scale: 0.98 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.98 }}
                  transition={{ duration: 0.2 }}
                  className="w-full h-full"
                >
                  {activeTab === "explore" && (
                    <HomeDashboard
                      onSearchCity={handleSearchCity}
                      isLoading={isLoading}
                      searchHistory={searchHistory}
                      onClearHistory={handleClearHistory}
                    />
                  )}
                  {activeTab === "map" && cityGuide && (
                    <MapWidget
                      spots={cityGuide.spots}
                      selectedSpot={selectedSpot}
                      onSelectSpot={setSelectedSpot}
                      favorites={favorites}
                      onToggleFavorite={handleToggleFavorite}
                      activeDayRoute={activeDayRouteSpots}
                    />
                  )}
                  {activeTab === "timeline" && cityGuide && (
                    <ItineraryTimeline
                      itinerary={cityGuide.itinerary}
                      spots={cityGuide.spots}
                      activeDay={activeDay}
                      setActiveDay={setActiveDay}
                      onSelectSpot={(spot) => {
                        setSelectedSpot(spot);
                        setActiveTab("map"); // auto-focus map and pin when timeline item clicked!
                      }}
                      visitedPlaces={visitedPlaces}
                      onToggleVisited={handleToggleVisited}
                    />
                  )}
                  {activeTab === "survival" && cityGuide && (
                    <SurvivalGuide
                      phrases={cityGuide.survivalPhrases}
                      currency={cityGuide.localCurrency}
                      etiquette={cityGuide.etiquetteTips}
                      weatherSummary={cityGuide.weatherSummary}
                      bestTimeToVisit={cityGuide.bestTimeToVisit}
                    />
                  )}
                  {activeTab === "chat" && cityGuide && (
                    <CompanionChat
                      city={cityGuide.cityName}
                      travelStyle={activeStyle}
                      chatHistory={chatHistory}
                      onSendMessage={handleSendChatMessage}
                      isLoading={isLoading}
                    />
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* ACTIVE BOTTOM NAV OVERLAY */}
          <BottomNav
            activeTab={activeTab}
            setActiveTab={(tab) => {
              setActiveTab(tab);
              // Auto reset selected spot details on switching tabs to avoid stray sheet overlays
              setSelectedSpot(null);
            }}
            hasActiveCity={cityGuide !== null}
            favoritesCount={favorites.length}
          />

          {/* ANDROID VIRTUAL HARDWARE KEYS */}
          <div className="bg-white border-t border-slate-100/50 flex justify-center items-center py-2 h-[38px] shrink-0 gap-16 text-slate-400 select-none">
            {/* Back triangular button */}
            <button 
              onClick={() => handleVirtualNavigation("back")}
              className="p-1 hover:text-slate-800 transition-colors"
              title="Virtual Back"
            >
              <Triangle size={14} className="rotate-270" strokeWidth={2.5} fill="none" />
            </button>
            
            {/* Home circular button */}
            <button 
              onClick={() => handleVirtualNavigation("home")}
              className="p-1 hover:text-slate-800 transition-colors"
              title="Virtual Home"
            >
              <Circle size={13} strokeWidth={2.5} fill="none" />
            </button>
            
            {/* Recents square button */}
            <button 
              onClick={() => handleVirtualNavigation("recents")}
              className="p-1 hover:text-slate-800 transition-colors"
              title="Virtual Recents"
            >
              <Square size={13} strokeWidth={2.5} fill="none" />
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}

// Minimal inline polyfill custom hook representing React useMemo for active day routing
function useEffectMemo<T>(factory: () => T, deps: any[]): T {
  const [val, setVal] = useState<T>(factory);
  useEffect(() => {
    setVal(factory());
  }, deps);
  return val;
}
