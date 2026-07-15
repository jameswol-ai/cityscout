import { useState, useRef, useEffect, FormEvent } from "react";
import { Message, TravelStyle } from "../types";
import { motion, AnimatePresence } from "motion/react";
import { 
  Send, 
  Map, 
  Compass, 
  MessageSquare, 
  HelpCircle,
  Clock,
  Sparkles,
  RefreshCw,
  Info
} from "lucide-react";

interface CompanionChatProps {
  city: string;
  travelStyle: TravelStyle;
  chatHistory: Message[];
  onSendMessage: (text: string) => Promise<void>;
  isLoading: boolean;
}

const QUICK_QUESTIONS = [
  "How does public transit work here?",
  "What local dishes must I absolutely try?",
  "Are there any tipping etiquette rules?",
  "What is a popular hidden secret spot here?",
];

export default function CompanionChat({
  city,
  travelStyle,
  chatHistory,
  onSendMessage,
  isLoading
}: CompanionChatProps) {
  const [inputText, setInputText] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const handleSend = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!inputText.trim() || isLoading) return;
    const text = inputText.trim();
    setInputText("");
    await onSendMessage(text);
  };

  const handleQuickQuestion = async (question: string) => {
    if (isLoading) return;
    await onSendMessage(question);
  };

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory, isLoading]);

  return (
    <div className="w-full h-full bg-slate-50 flex flex-col overflow-hidden" id="companion-chat-container">
      {/* Companion Chat Header */}
      <div className="bg-white px-4 py-3.5 border-b border-slate-100 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <div className="w-9 h-9 rounded-full bg-indigo-600 flex items-center justify-center text-white text-sm font-bold shadow-sm">
              <Compass size={18} className="animate-[spin_6s_linear_infinite]" />
            </div>
            <span className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-emerald-500 rounded-full border-2 border-white" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-slate-800 flex items-center gap-1">
              Local Guide AI
            </h3>
            <p className="text-[10px] text-slate-500">
              Personalized {travelStyle} advisor for {city}
            </p>
          </div>
        </div>

        <span className="text-[9px] bg-indigo-50 text-indigo-700 px-2 py-1 rounded-lg font-bold uppercase tracking-wider flex items-center gap-1">
          <Sparkles size={10} /> Live Assistant
        </span>
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3">
        {chatHistory.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-6 gap-3">
            <div className="w-12 h-12 rounded-full bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-500 shadow-sm">
              <MessageSquare size={20} />
            </div>
            <div>
              <h4 className="text-sm font-bold text-slate-700">Explore {city} together!</h4>
              <p className="text-xs text-slate-400 mt-1 max-w-[220px] mx-auto leading-relaxed">
                Ask me about language translations, safety rules, local transport, food, or tipping!
              </p>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {chatHistory.map((msg, index) => {
              const isUser = msg.role === "user";
              return (
                <div
                  key={index}
                  className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] rounded-2xl p-3.5 shadow-sm text-xs leading-relaxed ${
                      isUser
                        ? "bg-slate-900 text-white rounded-tr-none"
                        : "bg-white text-slate-800 border border-slate-100 rounded-tl-none"
                    }`}
                  >
                    <p>{msg.content}</p>
                    <span 
                      className={`text-[8px] mt-1.5 block text-right font-medium ${
                        isUser ? "text-slate-400" : "text-slate-400"
                      }`}
                    >
                      {msg.timestamp}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Loading Indicator */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-white border border-slate-100 text-slate-800 rounded-2xl rounded-tl-none p-3.5 shadow-sm text-xs flex items-center gap-2 max-w-[85%]">
              <RefreshCw size={12} className="animate-spin text-indigo-600 shrink-0" />
              <span className="text-slate-500 font-medium italic">Mapping local guide tips...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Footer Area - Quick chips & Input form */}
      <div className="bg-white border-t border-slate-100 p-3 shrink-0 pb-24">
        {/* Quick Questions Chips */}
        {chatHistory.length < 5 && (
          <div className="flex gap-1.5 overflow-x-auto no-scrollbar pb-3 mb-1">
            {QUICK_QUESTIONS.map((q, idx) => (
              <button
                key={idx}
                onClick={() => handleQuickQuestion(q)}
                disabled={isLoading}
                className="px-3 py-1.5 bg-slate-50 border border-slate-100 rounded-full text-[10px] font-semibold text-slate-600 hover:bg-slate-100 whitespace-nowrap shrink-0 transition-colors flex items-center gap-1"
              >
                <HelpCircle size={10} className="text-indigo-500" />
                {q}
              </button>
            ))}
          </div>
        )}

        {/* Message Input Form */}
        <form onSubmit={handleSend} className="flex gap-2 items-center">
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={isLoading}
            placeholder={`Ask about ${city}...`}
            className="flex-1 bg-slate-50 border border-slate-100 rounded-xl px-3.5 py-2.5 text-xs outline-none focus:bg-white focus:ring-1 focus:ring-indigo-500 text-slate-800"
          />
          <button
            type="submit"
            disabled={!inputText.trim() || isLoading}
            className={`p-2.5 rounded-xl text-white transition-all ${
              inputText.trim() && !isLoading
                ? "bg-indigo-600 hover:bg-indigo-700 shadow-md"
                : "bg-slate-300 cursor-not-allowed"
            }`}
          >
            <Send size={15} />
          </button>
        </form>
      </div>
    </div>
  );
}
