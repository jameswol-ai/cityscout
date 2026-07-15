import { useState } from "react";
import { DayItinerary, Spot, SpotCategory } from "../types";
import { motion, AnimatePresence } from "motion/react";
import { 
  CheckCircle2, 
  Circle, 
  Clock, 
  MapPin, 
  Navigation, 
  Compass, 
  Utensils, 
  TreePine, 
  Sparkles,
  Award
} from "lucide-react";

interface ItineraryTimelineProps {
  itinerary: DayItinerary[];
  spots: Spot[];
  activeDay: number;
  setActiveDay: (day: number) => void;
  onSelectSpot: (spot: Spot | null) => void;
  visitedPlaces: string[];
  onToggleVisited: (id: string) => void;
}

const CATEGORY_ICONS: Record<SpotCategory, any> = {
  landmark: Compass,
  food: Utensils,
  nature: TreePine,
  secret: Sparkles
};

const CATEGORY_COLORS: Record<SpotCategory, { text: string; bg: string; dot: string }> = {
  landmark: { text: "text-amber-700", bg: "bg-amber-100", dot: "bg-amber-500" },
  food: { text: "text-emerald-700", bg: "bg-emerald-100", dot: "bg-emerald-500" },
  nature: { text: "text-teal-700", bg: "bg-teal-100", dot: "bg-teal-500" },
  secret: { text: "text-purple-700", bg: "bg-purple-100", dot: "bg-purple-500" }
};

export default function ItineraryTimeline({
  itinerary,
  spots,
  activeDay,
  setActiveDay,
  onSelectSpot,
  visitedPlaces,
  onToggleVisited
}: ItineraryTimelineProps) {
  const currentDayData = itinerary.find(day => day.dayNumber === activeDay) || itinerary[0];

  // Helper to find a spot's details by ID
  const getSpotById = (id: string): Spot | undefined => {
    return spots.find(s => s.id === id);
  };

  // Calculate day completion rate
  const completionStats = useMemoCompletionStats(currentDayData?.activities || [], visitedPlaces);

  return (
    <div className="w-full h-full bg-slate-50 flex flex-col overflow-hidden" id="timeline-container">
      {/* Day Selector Header Tabs */}
      <div className="bg-white border-b border-slate-100 px-4 py-3 shrink-0">
        <div className="flex gap-2 overflow-x-auto no-scrollbar py-0.5">
          {itinerary.map(day => {
            const isSelected = activeDay === day.dayNumber;
            return (
              <button
                key={day.dayNumber}
                onClick={() => setActiveDay(day.dayNumber)}
                className={`px-4 py-2 rounded-2xl text-xs font-semibold whitespace-nowrap transition-all ${
                  isSelected
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                Day {day.dayNumber}
              </button>
            );
          })}
        </div>

        {/* Day theme */}
        {currentDayData && (
          <div className="mt-3 flex justify-between items-center gap-3">
            <div>
              <span className="text-[9px] uppercase tracking-wider font-bold text-indigo-600">Daily Track</span>
              <h3 className="text-sm font-bold text-slate-800 leading-snug">
                {currentDayData.theme}
              </h3>
            </div>
            
            {/* Completion Ring/Metric */}
            <div className="flex items-center gap-2 bg-slate-50 border border-slate-100 px-2.5 py-1 rounded-xl shrink-0">
              <Award size={13} className={completionStats.percent === 100 ? "text-amber-500" : "text-indigo-500"} />
              <span className="text-[10px] font-bold text-slate-600">
                {completionStats.visitedCount}/{completionStats.totalCount} visited
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Timeline Scroll Container */}
      <div className="flex-1 overflow-y-auto px-4 py-5 pb-24">
        {completionStats.percent === 100 && (
          <motion.div 
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="mb-5 bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 p-3 rounded-2xl flex items-center gap-3"
          >
            <div className="bg-amber-100 p-2 rounded-xl text-amber-600 shrink-0">
              <Award size={18} />
            </div>
            <div>
              <h4 className="text-xs font-bold text-amber-900">Day {activeDay} Completed!</h4>
              <p className="text-[10px] text-amber-700 leading-snug">Awesome job! You have explored every single recommendation on this route.</p>
            </div>
          </motion.div>
        )}

        <div className="relative border-l-2 border-slate-200 pl-6 ml-3 flex flex-col gap-6">
          {currentDayData?.activities.map((activity, idx) => {
            const spot = getSpotById(activity.spotId);
            const isVisited = visitedPlaces.includes(activity.spotId);
            const CatIcon = spot ? CATEGORY_ICONS[spot.category] : Compass;
            const colors = spot ? CATEGORY_COLORS[spot.category] : { text: "text-slate-600", bg: "bg-slate-100", dot: "bg-slate-500" };

            return (
              <div key={idx} className="relative group">
                {/* Timeline Dot */}
                <span className={`absolute -left-[31px] top-1.5 w-4 h-4 rounded-full border-2 border-white shadow-sm flex items-center justify-center transition-all ${
                  isVisited ? "bg-emerald-500" : colors.dot
                }`}>
                  <span className="w-1 h-1 rounded-full bg-white" />
                </span>

                {/* Main timeline item card */}
                <div className="bg-white rounded-2xl border border-slate-100 shadow-sm p-3.5 transition-all hover:shadow-md hover:border-slate-200">
                  <div className="flex items-start justify-between gap-3">
                    {/* Time of Visit */}
                    <div className="flex items-center gap-1 text-[10px] text-indigo-600 font-bold bg-indigo-50 px-2 py-0.5 rounded-lg shrink-0">
                      <Clock size={11} />
                      <span>{activity.time}</span>
                    </div>

                    {/* Completion Checkbox */}
                    <button
                      onClick={() => onToggleVisited(activity.spotId)}
                      className={`text-xs font-medium flex items-center gap-1 shrink-0 p-1 rounded-lg transition-colors ${
                        isVisited 
                          ? "text-emerald-600 hover:bg-emerald-50" 
                          : "text-slate-400 hover:text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      {isVisited ? (
                        <CheckCircle2 size={16} className="text-emerald-500" />
                      ) : (
                        <Circle size={16} />
                      )}
                    </button>
                  </div>

                  {/* Spot Title & Category */}
                  <div className="mt-2.5">
                    <h4 
                      onClick={() => spot && onSelectSpot(spot)}
                      className="text-sm font-bold text-slate-800 hover:text-indigo-600 cursor-pointer flex items-center gap-1.5 leading-snug"
                    >
                      {activity.spotName}
                    </h4>
                    {spot && (
                      <span className={`inline-flex items-center gap-1 mt-1 text-[9px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${colors.bg} ${colors.text}`}>
                        <CatIcon size={9} /> {spot.category}
                      </span>
                    )}
                  </div>

                  {/* Activity Specific advice description */}
                  <p className="text-xs text-slate-500 mt-2 leading-relaxed">
                    {activity.activityDescription}
                  </p>

                  {/* Link Map button */}
                  {spot && (
                    <div className="mt-3.5 pt-3 border-t border-slate-50 flex items-center justify-between">
                      <span className="text-[10px] text-slate-400 font-medium">
                        ⏱️ {spot.recommendedDuration} • 🚶 {spot.activityLevel} activity
                      </span>
                      <button
                        onClick={() => onSelectSpot(spot)}
                        className="text-[10px] text-indigo-600 hover:text-indigo-800 font-bold flex items-center gap-1"
                      >
                        <MapPin size={11} /> Find on Map
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// Stats helper
function useMemoCompletionStats(activities: any[], visitedPlaces: string[]) {
  const totalCount = activities.length;
  if (totalCount === 0) return { totalCount: 0, visitedCount: 0, percent: 0 };
  
  const visitedCount = activities.filter(act => visitedPlaces.includes(act.spotId)).length;
  const percent = Math.round((visitedCount / totalCount) * 100);

  return { totalCount, visitedCount, percent };
}
