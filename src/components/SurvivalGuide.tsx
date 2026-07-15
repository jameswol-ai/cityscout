import { useState } from "react";
import { SurvivalPhrase } from "../types";
import { 
  motion 
} from "motion/react";
import { 
  Volume2, 
  HelpCircle, 
  Coins, 
  Globe2, 
  Compass, 
  TrendingUp, 
  FlameKindling,
  AlertTriangle,
  Lightbulb
} from "lucide-react";

interface SurvivalGuideProps {
  phrases: SurvivalPhrase[];
  currency: string;
  etiquette: string[];
  weatherSummary: string;
  bestTimeToVisit: string;
}

export default function SurvivalGuide({
  phrases,
  currency,
  etiquette,
  weatherSummary,
  bestTimeToVisit
}: SurvivalGuideProps) {
  const [usdAmount, setUsdAmount] = useState<string>("100");
  const [speakingIndex, setSpeakingIndex] = useState<number | null>(null);

  // Parse exchange rate from the currency name or fallback to estimate
  const rateInfo = useMemoExchangeRate(currency);

  const localAmount = (parseFloat(usdAmount) || 0) * rateInfo.rate;

  // Web Speech synthesis to read the survival phrase out loud
  const speakPhrase = (phrase: string, index: number) => {
    if (!window.speechSynthesis) {
      alert("Text-to-speech is not supported in this browser.");
      return;
    }

    // Cancel anything playing
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(phrase);
    
    // Guess lang based on currency / context
    if (currency.includes("Yen") || currency.includes("¥")) {
      utterance.lang = "ja-JP";
    } else if (currency.includes("Euro") || currency.includes("€")) {
      utterance.lang = "fr-FR";
    } else if (currency.includes("Won") || currency.includes("₩")) {
      utterance.lang = "ko-KR";
    } else if (currency.includes("Peso")) {
      utterance.lang = "es-MX";
    } else {
      utterance.lang = "en-US";
    }

    utterance.onstart = () => setSpeakingIndex(index);
    utterance.onend = () => setSpeakingIndex(null);
    utterance.onerror = () => setSpeakingIndex(null);

    window.speechSynthesis.speak(utterance);
  };

  return (
    <div className="w-full h-full bg-slate-50 overflow-y-auto px-4 py-5 flex flex-col gap-5 pb-24" id="survival-guide-container">
      {/* Intro Header */}
      <div>
        <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
          <Globe2 className="text-indigo-600" size={20} /> Local Guide & Survival Tools
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Essential tools to blend in like a local, calculate expenses, and survive the streets!
        </p>
      </div>

      {/* Weather & Best Visit Quick Cards */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-white p-3.5 rounded-2xl shadow-sm border border-slate-100">
          <span className="text-[10px] uppercase tracking-wider font-semibold text-slate-400 flex items-center gap-1">
            <Compass size={11} className="text-amber-500" /> Season & Timing
          </span>
          <h4 className="text-xs font-bold text-slate-800 mt-1">Best time to visit</h4>
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">{bestTimeToVisit}</p>
        </div>

        <div className="bg-white p-3.5 rounded-2xl shadow-sm border border-slate-100">
          <span className="text-[10px] uppercase tracking-wider font-semibold text-slate-400 flex items-center gap-1">
            <FlameKindling size={11} className="text-indigo-500" /> Pack & Prepare
          </span>
          <h4 className="text-xs font-bold text-slate-800 mt-1">Weather guide</h4>
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">{weatherSummary}</p>
        </div>
      </div>

      {/* Currency Converter Widget */}
      <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
        <h3 className="text-sm font-bold text-slate-800 flex items-center gap-1.5 mb-3">
          <Coins className="text-emerald-500" size={16} /> Quick Exchange Calculator
        </h3>
        
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3 bg-slate-50 px-3.5 py-2.5 rounded-xl border border-slate-100">
            <div className="flex flex-col flex-1">
              <span className="text-[9px] uppercase tracking-wider font-semibold text-slate-400">You Pay (USD)</span>
              <input
                type="number"
                value={usdAmount}
                onChange={(e) => setUsdAmount(e.target.value)}
                className="bg-transparent border-none outline-none font-bold text-slate-800 text-sm w-full p-0"
                placeholder="0.00"
              />
            </div>
            <span className="text-xs font-bold text-slate-500">USD ($)</span>
          </div>

          <div className="flex justify-center">
            <div className="bg-indigo-50 text-indigo-600 rounded-full p-1.5 border border-indigo-100">
              <TrendingUp size={14} className="rotate-90" />
            </div>
          </div>

          <div className="flex items-center gap-3 bg-slate-900 px-3.5 py-2.5 rounded-xl border border-slate-800">
            <div className="flex flex-col flex-1">
              <span className="text-[9px] uppercase tracking-wider font-semibold text-slate-500">You Get</span>
              <span className="font-bold text-white text-sm">
                {localAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
            <span className="text-xs font-bold text-indigo-300">{rateInfo.symbol} {rateInfo.code}</span>
          </div>

          <div className="text-[10px] text-slate-400 flex items-center gap-1.5 justify-center mt-1">
            <Lightbulb size={12} className="text-amber-500" />
            <span>Estimated local rate: 1 USD ≈ {rateInfo.rate} {rateInfo.code}</span>
          </div>
        </div>
      </div>

      {/* Cultural Etiquette */}
      <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
        <h3 className="text-sm font-bold text-slate-800 flex items-center gap-1.5 mb-3">
          <AlertTriangle className="text-amber-500" size={16} /> Etiquette & Culture Tips
        </h3>
        <div className="flex flex-col gap-2.5">
          {etiquette.map((tip, idx) => (
            <div key={idx} className="flex gap-2.5 items-start">
              <span className="bg-amber-50 text-amber-700 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold shrink-0">
                {idx + 1}
              </span>
              <p className="text-xs text-slate-600 leading-relaxed pt-0.5">{tip}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Survival Phrasebook */}
      <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
        <h3 className="text-sm font-bold text-slate-800 flex items-center gap-1.5 mb-2">
          <HelpCircle className="text-indigo-500" size={16} /> Survival Local Phrasebook
        </h3>
        <p className="text-[11px] text-slate-400 mb-4 leading-relaxed">
          Tap the speech bubble to listen to local pronunciation in its native accent!
        </p>

        <div className="flex flex-col gap-3">
          {phrases.map((item, index) => (
            <div 
              key={index} 
              className="p-3 bg-slate-50 rounded-xl border border-slate-100 flex justify-between items-center gap-3 transition-colors hover:bg-slate-100/50"
            >
              <div className="flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="font-bold text-slate-800 text-sm font-mono">{item.phrase}</span>
                  <span className="text-[10px] text-slate-400 italic">({item.pronunciation})</span>
                </div>
                <div className="text-xs text-slate-600 font-medium mt-1">
                  {item.meaning}
                </div>
              </div>

              <button
                onClick={() => speakPhrase(item.phrase, index)}
                className={`p-2 rounded-full transition-all shrink-0 ${
                  speakingIndex === index 
                    ? "bg-indigo-600 text-white animate-pulse" 
                    : "bg-white border border-slate-200 text-indigo-600 hover:bg-indigo-50"
                }`}
              >
                <Volume2 size={15} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Custom hook / helper to estimate exchange rate from the currency string
function useMemoExchangeRate(currencyStr: string) {
  const norm = currencyStr.toLowerCase();
  if (norm.includes("yen") || norm.includes("¥") || norm.includes("jpy")) {
    return { code: "JPY", symbol: "¥", rate: 154.8 };
  }
  if (norm.includes("euro") || norm.includes("€") || norm.includes("eur")) {
    return { code: "EUR", symbol: "€", rate: 0.92 };
  }
  if (norm.includes("pound") || norm.includes("£") || norm.includes("gbp")) {
    return { code: "GBP", symbol: "£", rate: 0.78 };
  }
  if (norm.includes("won") || norm.includes("₩") || norm.includes("krw")) {
    return { code: "KRW", symbol: "₩", rate: 1380.0 };
  }
  if (norm.includes("peso") || norm.includes("mxn")) {
    return { code: "MXN", symbol: "$", rate: 17.5 };
  }
  if (norm.includes("dollar") || norm.includes("$") || norm.includes("aud") || norm.includes("cad")) {
    if (norm.includes("australian") || norm.includes("aud")) {
      return { code: "AUD", symbol: "$", rate: 1.51 };
    }
    return { code: "CAD", symbol: "$", rate: 1.36 };
  }
  if (norm.includes("rupee") || norm.includes("₹") || norm.includes("inr")) {
    return { code: "INR", symbol: "₹", rate: 83.5 };
  }
  if (norm.includes("franc") || norm.includes("chf")) {
    return { code: "CHF", symbol: "Fr.", rate: 0.89 };
  }
  if (norm.includes("real") || norm.includes("r$") || norm.includes("brl")) {
    return { code: "BRL", symbol: "R$", rate: 5.4 };
  }
  
  // Dynamic parsing fallback
  const firstSymbol = currencyStr.match(/[^A-Za-z0-9\s]/)?.[0] || "$";
  const firstCode = currencyStr.match(/[A-Z]{3}/)?.[0] || "LC";
  return { code: firstCode, symbol: firstSymbol, rate: 1.0 };
}
