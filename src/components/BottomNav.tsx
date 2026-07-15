import { Spot } from "../types";
import { 
  Compass, 
  Map, 
  Calendar, 
  ShieldAlert, 
  MessageSquareCode
} from "lucide-react";

export type TabType = "explore" | "map" | "timeline" | "survival" | "chat";

interface BottomNavProps {
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
  hasActiveCity: boolean;
  favoritesCount: number;
}

export default function BottomNav({
  activeTab,
  setActiveTab,
  hasActiveCity,
  favoritesCount
}: BottomNavProps) {
  const navItems = [
    { id: "explore" as TabType, label: "Explore", icon: Compass, requiresCity: false },
    { id: "map" as TabType, label: "Interactive Map", icon: Map, requiresCity: true },
    { id: "timeline" as TabType, label: "Timeline", icon: Calendar, requiresCity: true },
    { id: "survival" as TabType, label: "Local Info", icon: ShieldAlert, requiresCity: true },
    { id: "chat" as TabType, label: "AI Companion", icon: MessageSquareCode, requiresCity: true }
  ];

  return (
    <div className="bg-white border-t border-slate-100 flex justify-around items-center h-[58px] shrink-0 px-2" id="bottom-navigation-bar">
      {navItems.map((item) => {
        const Icon = item.icon;
        const isActive = activeTab === item.id;
        const isDisabled = item.requiresCity && !hasActiveCity;

        return (
          <button
            key={item.id}
            onClick={() => !isDisabled && setActiveTab(item.id)}
            disabled={isDisabled}
            className={`flex flex-col items-center justify-center flex-1 py-1.5 transition-all relative ${
              isDisabled 
                ? "opacity-35 cursor-not-allowed" 
                : "cursor-pointer"
            }`}
          >
            <div className={`p-1 px-3.5 rounded-full transition-all flex items-center justify-center ${
              isActive 
                ? "bg-indigo-100 text-indigo-700 font-bold" 
                : "text-slate-500 hover:text-slate-800"
            }`}>
              <Icon size={18} strokeWidth={isActive ? 2.5 : 2} className="transition-transform duration-200" />
            </div>
            <span className={`text-[9px] mt-1 transition-all ${
              isActive ? "font-bold text-indigo-700" : "text-slate-400 font-medium"
            }`}>
              {item.label}
            </span>

            {/* Favorites dot badge if map tab */}
            {item.id === "map" && favoritesCount > 0 && (
              <span className="absolute top-1 right-6 bg-rose-500 text-white font-bold text-[8px] w-4 h-4 rounded-full flex items-center justify-center">
                {favoritesCount}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
