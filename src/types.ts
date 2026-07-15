export type SpotCategory = "landmark" | "food" | "nature" | "secret";
export type TimeOfDay = "morning" | "afternoon" | "evening" | "night";
export type ActivityLevel = "low" | "medium" | "high";

export interface SurvivalPhrase {
  phrase: string;
  meaning: string;
  pronunciation: string;
}

export interface Spot {
  id: string;
  name: string;
  category: SpotCategory;
  description: string;
  bestTimeOfDay: TimeOfDay;
  activityLevel: ActivityLevel;
  latOffset: number; // grid coordinates on custom interactive map
  lngOffset: number;
  recommendedDuration: string;
}

export interface Activity {
  time: string;
  spotName: string;
  activityDescription: string;
  spotId: string;
}

export interface DayItinerary {
  dayNumber: number;
  theme: string;
  activities: Activity[];
}

export interface CityGuide {
  cityName: string;
  country: string;
  description: string;
  bestTimeToVisit: string;
  weatherSummary: string;
  localCurrency: string;
  localGreeting: string;
  etiquetteTips: string[];
  survivalPhrases: SurvivalPhrase[];
  spots: Spot[];
  itinerary: DayItinerary[];
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export type TravelStyle = "Balanced" | "Foodie" | "Historic" | "Nature" | "Budget" | "Adventure";
