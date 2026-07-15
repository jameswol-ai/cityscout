import React, { useState, useMemo } from "react";
import { Spot, SpotCategory } from "../types";
import { 
  motion, 
  AnimatePresence 
} from "motion/react";
import { 
  Compass, 
  MapPin, 
  Utensils, 
  TreePine, 
  Sparkles, 
  Clock, 
  Activity, 
  Navigation, 
  Heart,
  Layers,
  ChevronUp,
  BookmarkCheck
} from "lucide-react";

interface MapWidgetProps {
  spots: Spot[];
  selectedSpot: Spot | null;
  onSelectSpot: (spot: Spot | null) => void;
  favorites: string[];
  onToggleFavorite: (id: string) => void;
  activeDayRoute?: Spot[]; // Spots in order for the selected day's route
}

const CATEGORY_COLORS: Record<SpotCategory, { bg: string; text: string; border: string; icon: any }> = {
  landmark: { bg: "bg-amber-100", text: "text-amber-700", border: "border-amber-300", icon: Compass },
  food: { bg: "bg-emerald-100", text: "text-emerald-700", border: "border-emerald-300", icon: Utensils },
  nature: { bg: "bg-teal-100", text: "text-teal-700", border: "border-teal-300", icon: TreePine },
  secret: { bg: "bg-purple-100", text: "text-purple-700", border: "border-purple-300", icon: Sparkles }
};

export default function MapWidget({
  spots,
  selectedSpot,
  onSelectSpot,
  favorites,
  onToggleFavorite,
  activeDayRoute = []
}: MapWidgetProps) {
  const [filterCategory, setFilterCategory] = useState<SpotCategory | "all">("all");
  const [mapType, setMapType] = useState<"standard" | "transit" | "terrain">("standard");

  const filteredSpots = useMemo(() => {
    if (filterCategory === "all") return spots;
    return spots.filter(s => s.category === filterCategory);
  }, [spots, filterCategory]);

  // Convert lat/lng offsets (-80 to 80) into SVG coordinates (50 to 450)
  const mapCoords = (offset: number, size: number) => {
    // scale from [-80, 80] to [40, size - 40]
    const minOffset = -80;
    const maxOffset = 80;
    const minCoord = 40;
    const maxCoord = size - 40;
    
    return minCoord + ((offset - minOffset) / (maxOffset - minOffset)) * (maxCoord - minCoord);
  };

  const svgSize = 500;

  // Generate some aesthetic background map vectors using the cityName seed or just fixed layouts
  // so the grid feels like a real city with roads, a river, and a large park.
  const riverPath = useMemo(() => {
    return `M 0,${svgSize * 0.4} Q ${svgSize * 0.25},${svgSize * 0.3} ${svgSize * 0.5},${svgSize * 0.55} T ${svgSize},${svgSize * 0.5}`;
  }, []);

  const majorRoad1 = `M 0,${svgSize * 0.5} L ${svgSize},${svgSize * 0.5}`;
  const majorRoad2 = `M ${svgSize * 0.5},0 L ${svgSize * 0.5},${svgSize}`;
  const diagonalRoad = `M 0,0 L ${svgSize},${svgSize}`;

  // Find sequence coordinates for route drawing
  const routePoints = useMemo(() => {
    if (!activeDayRoute || activeDayRoute.length === 0) return "";
    return activeDayRoute
      .map(spot => {
        const x = mapCoords(spot.lngOffset, svgSize);
        const y = mapCoords(spot.latOffset, svgSize);
        return `${x},${y}`;
      })
      .join(" L ");
  }, [activeDayRoute]);

  return (
    <div className="relative w-full h-full bg-slate-50 flex flex-col overflow-hidden" id="map-widget-container">
      {/* Map Control Header */}
      <div className="absolute top-3 left-3 right-3 z-10 flex flex-col gap-2 pointer-events-none">
        {/* Search / Filters Overlay */}
        <div className="bg-white/95 backdrop-blur shadow-md rounded-2xl p-2.5 flex flex-col gap-2 pointer-events-auto border border-slate-100">
          <div className="flex items-center justify-between px-1">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
              <Layers size={14} /> City Map Layers
            </span>
            <div className="flex bg-slate-100 p-0.5 rounded-lg text-xs font-medium">
              {(["standard", "transit", "terrain"] as const).map(type => (
                <button
                  key={type}
                  onClick={() => setMapType(type)}
                  className={`px-2.5 py-1 rounded-md transition-all capitalize ${
                    mapType === type ? "bg-white text-indigo-600 shadow-sm" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>

          {/* Category Pills */}
          <div className="flex gap-1 overflow-x-auto no-scrollbar py-0.5">
            <button
              onClick={() => setFilterCategory("all")}
              className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-all flex items-center gap-1 ${
                filterCategory === "all"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              All Spots
            </button>
            {(["landmark", "food", "nature", "secret"] as const).map(cat => {
              const config = CATEGORY_COLORS[cat];
              const Icon = config.icon;
              return (
                <button
                  key={cat}
                  onClick={() => setFilterCategory(cat)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-all flex items-center gap-1 ${
                    filterCategory === cat
                      ? "bg-slate-900 text-white shadow-sm"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  <Icon size={12} className={filterCategory === cat ? "text-white" : config.text} />
                  <span className="capitalize">{cat === "secret" ? "Secrets" : cat}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Route Active Banner */}
        {activeDayRoute.length > 0 && (
          <motion.div 
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-indigo-50 border border-indigo-200 text-indigo-800 px-3 py-1.5 rounded-xl text-xs font-medium self-start pointer-events-auto flex items-center gap-1.5 shadow-sm"
          >
            <Navigation size={13} className="animate-pulse text-indigo-600" />
            <span>Showing route for Selected Day ({activeDayRoute.length} stops)</span>
          </motion.div>
        )}
      </div>

      {/* Map Interactive Stage */}
      <div className="flex-1 w-full bg-[#EAEDE8] relative overflow-hidden flex items-center justify-center">
        {/* Styled Vector Map Base */}
        <svg
          viewBox={`0 0 ${svgSize} ${svgSize}`}
          className="w-full h-full max-h-[85vh] transition-all duration-500"
          style={{
            background: mapType === "terrain" ? "#DFE3DA" : mapType === "transit" ? "#E3E4E6" : "#EAEDE8"
          }}
        >
          {/* Grid lines (Aesthetic coordinate look) */}
          <g stroke="#000000" strokeOpacity="0.04" strokeWidth="1">
            {Array.from({ length: 10 }).map((_, i) => {
              const pos = (svgSize / 10) * i;
              return (
                <React.Fragment key={i}>
                  <line x1={pos} y1="0" x2={pos} y2={svgSize} />
                  <line x1="0" y1={pos} x2={svgSize} y2={pos} />
                </React.Fragment>
              );
            })}
          </g>

          {/* River / Water Body */}
          <path
            d={riverPath}
            fill="none"
            stroke="#A3C6E5"
            strokeWidth={mapType === "terrain" ? "24" : "18"}
            strokeLinecap="round"
            className="transition-all duration-300"
          />
          {mapType === "terrain" && (
            <path
              d={riverPath}
              fill="none"
              stroke="#B9D5ED"
              strokeWidth="10"
              strokeLinecap="round"
            />
          )}

          {/* Green parks */}
          <rect x={svgSize * 0.1} y={svgSize * 0.1} width="120" height="90" rx="20" fill="#CDE2C4" fillOpacity="0.7" />
          <circle cx={svgSize * 0.8} cy={svgSize * 0.25} r="70" fill="#CDE2C4" fillOpacity="0.7" />
          <rect x={svgSize * 0.6} y={svgSize * 0.7} width="140" height="110" rx="30" fill="#CDE2C4" fillOpacity="0.7" />

          {/* Transit Lines overlay */}
          {mapType === "transit" && (
            <g strokeOpacity="0.6" strokeWidth="3" fill="none">
              <path d="M 50,0 L 50,500" stroke="#EF4444" strokeDasharray="6,4" />
              <path d="M 0,250 L 500,250" stroke="#3B82F6" strokeDasharray="6,4" />
              <path d="M 0,450 Q 250,200 500,50" stroke="#10B981" strokeDasharray="6,4" />
            </g>
          )}

          {/* Road Grids */}
          <g stroke="#FFFFFF" strokeWidth="6" strokeLinecap="round" strokeOpacity="0.8">
            <path d={majorRoad1} />
            <path d={majorRoad2} />
            <path d={diagonalRoad} />
            {/* Some side streets */}
            <line x1="100" y1="0" x2="100" y2="500" strokeWidth="3" />
            <line x1="400" y1="0" x2="400" y2="500" strokeWidth="3" />
            <line x1="0" y1="150" x2="500" y2="150" strokeWidth="3" />
            <line x1="0" y1="350" x2="500" y2="350" strokeWidth="3" />
          </g>

          {/* Road Labels (for aesthetic city feeling) */}
          <g fill="#888F80" fontSize="8" fontFamily="sans-serif" fontWeight="bold">
            <text x="15" y={svgSize * 0.49} transform={`rotate(0, 15, ${svgSize * 0.49})`}>BROADWAY AVE</text>
            <text x={svgSize * 0.51} y="40" transform={`rotate(90, ${svgSize * 0.51}, 40)`}>CENTRAL BLVD</text>
            <text x="250" y="245" fill="#3B82F6" fontSize="7">METRO RED LINE</text>
          </g>

          {/* Route Connection Path */}
          {routePoints && (
            <g>
              <path
                d={`M ${routePoints}`}
                fill="none"
                stroke="#6366F1"
                strokeWidth="4"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeDasharray="8,6"
                className="animate-[dash_10s_linear_infinite]"
              />
              <path
                d={`M ${routePoints}`}
                fill="none"
                stroke="#818CF8"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </g>
          )}

          {/* Active Pins */}
          <g>
            {filteredSpots.map((spot, index) => {
              const x = mapCoords(spot.lngOffset, svgSize);
              const y = mapCoords(spot.latOffset, svgSize);
              const isSelected = selectedSpot?.id === spot.id;
              const config = CATEGORY_COLORS[spot.category];
              const isFavorite = favorites.includes(spot.id);

              return (
                <g 
                  key={spot.id} 
                  className="cursor-pointer group"
                  onClick={() => onSelectSpot(isSelected ? null : spot)}
                >
                  {/* Outer pulse effect */}
                  {isSelected && (
                    <circle cx={x} cy={y} r="16" fill="#6366F1" fillOpacity="0.25" className="animate-ping" style={{ transformOrigin: `${x}px ${y}px` }} />
                  )}

                  {/* Pin Base Shadow */}
                  <ellipse cx={x} cy={y + 2} rx="6" ry="2" fill="#000" fillOpacity="0.15" />

                  {/* Marker Pin shape */}
                  <motion.path
                    d={`M ${x},${y} C ${x - 10},${y - 12} ${x - 10},${y - 24} ${x},${y - 24} C ${x + 10},${y - 24} ${x + 10},${y - 12} ${x},${y} Z`}
                    fill={isSelected ? "#4F46E5" : isFavorite ? "#EF4444" : "#1E293B"}
                    stroke="#FFFFFF"
                    strokeWidth="1.5"
                    animate={{ y: isSelected ? -4 : 0 }}
                    transition={{ type: "spring", stiffness: 300, damping: 15 }}
                  />

                  {/* Inner Icon Indicator */}
                  <circle cx={x} cy={y - 14} r="5" fill="#FFFFFF" />
                  <g transform={`translate(${x - 4}, ${y - 18}) scale(0.6)`}>
                    <config.icon size={14} className={isSelected ? "text-indigo-600" : isFavorite ? "text-red-500" : "text-slate-800"} />
                  </g>

                  {/* Mini Tooltip */}
                  <g className="opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none">
                    <rect x={x - 60} y={y - 48} width="120" height="20" rx="6" fill="#1E293B" />
                    <polygon points={`${x},${y-24} ${x-4},${y-28} ${x+4},${y-28}`} fill="#1E293B" />
                    <text x={x} y={y - 35} fill="#FFFFFF" fontSize="8" textAnchor="middle" fontWeight="600">
                      {spot.name.length > 20 ? `${spot.name.slice(0, 18)}...` : spot.name}
                    </text>
                  </g>
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      {/* Android Bottom Sheet Details Panel */}
      <AnimatePresence>
        {selectedSpot && (
          <motion.div
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 25, stiffness: 220 }}
            className="absolute bottom-0 left-0 right-0 bg-white rounded-t-3xl shadow-2xl border-t border-slate-100 z-20 pointer-events-auto flex flex-col max-h-[45%]"
          >
            {/* Sheet Notch */}
            <div 
              className="w-full flex justify-center py-2.5 cursor-pointer hover:bg-slate-50 rounded-t-3xl"
              onClick={() => onSelectSpot(null)}
            >
              <div className="w-12 h-1 bg-slate-300 rounded-full" />
            </div>

            {/* Scrollable details */}
            <div className="px-5 pb-6 overflow-y-auto">
              <div className="flex justify-between items-start gap-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${CATEGORY_COLORS[selectedSpot.category].bg} ${CATEGORY_COLORS[selectedSpot.category].text}`}>
                      {selectedSpot.category}
                    </span>
                    <span className="text-xs text-slate-500 font-medium capitalize flex items-center gap-1">
                      <Clock size={11} /> {selectedSpot.bestTimeOfDay}
                    </span>
                  </div>
                  <h3 className="text-lg font-bold text-slate-900 leading-tight">
                    {selectedSpot.name}
                  </h3>
                </div>

                <div className="flex gap-1.5">
                  <button
                    onClick={() => onToggleFavorite(selectedSpot.id)}
                    className={`p-2.5 rounded-full transition-all border ${
                      favorites.includes(selectedSpot.id)
                        ? "bg-rose-50 border-rose-200 text-rose-500"
                        : "bg-slate-50 border-slate-200 text-slate-400 hover:text-slate-600"
                    }`}
                  >
                    <Heart size={18} fill={favorites.includes(selectedSpot.id) ? "currentColor" : "none"} />
                  </button>
                  <button
                    onClick={() => onSelectSpot(null)}
                    className="p-2.5 bg-slate-100 text-slate-500 hover:bg-slate-200 rounded-full text-xs font-semibold"
                  >
                    Close
                  </button>
                </div>
              </div>

              <p className="mt-3 text-sm text-slate-600 leading-relaxed">
                {selectedSpot.description}
              </p>

              {/* Grid attributes */}
              <div className="grid grid-cols-2 gap-3 mt-4">
                <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100 flex items-center gap-2">
                  <Activity size={15} className="text-indigo-500" />
                  <div>
                    <div className="text-[10px] text-slate-400 font-medium uppercase">Activity Level</div>
                    <div className="text-xs font-bold text-slate-700 capitalize">{selectedSpot.activityLevel}</div>
                  </div>
                </div>

                <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100 flex items-center gap-2">
                  <Clock size={15} className="text-indigo-500" />
                  <div>
                    <div className="text-[10px] text-slate-400 font-medium uppercase">Suggested Visit</div>
                    <div className="text-xs font-bold text-slate-700">{selectedSpot.recommendedDuration}</div>
                  </div>
                </div>
              </div>

              {/* Get Directions simulation */}
              <div className="mt-5 flex gap-2">
                <button 
                  onClick={() => {
                    alert(`Routing your path to ${selectedSpot.name}... Enjoy exploring!`);
                  }}
                  className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2.5 px-4 rounded-xl text-xs flex items-center justify-center gap-1.5 transition-colors shadow-sm"
                >
                  <Navigation size={14} /> Navigate Here
                </button>
                {favorites.includes(selectedSpot.id) && (
                  <div className="bg-emerald-50 text-emerald-700 px-3 py-2.5 rounded-xl border border-emerald-200 text-xs font-medium flex items-center gap-1.5">
                    <BookmarkCheck size={14} /> Saved in Favorites
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
