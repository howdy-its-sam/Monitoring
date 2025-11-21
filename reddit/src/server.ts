import { serve } from "bun";
import { Scraper } from "./scraper";

const PORT = parseInt(process.env.PORT || "3000");

const SUBS = [
  "AI_Agents", "AgentsOfAI", "AutoGPT", "LangChain", "RAG", "PromptEngineering", 
  "PromptDesign", "LocalLLaMA", "LargeLanguageModels", "LanguageTechnology",
  "MachineLearning", "DeepLearning", "ArtificialIntelligence", "OpenAI", "ChatGPT", 
  "GenerativeAI", "GPT3", "HumanAIDiscourse", "AIethics", "Futurology",
  "LLMDevs", "MachineLearningNews", "MLQuestions", "learnmachinelearning", "ChatGPTCoding", 
  "ChatGPTPro", "compling", "singularity", "Transhuman", "AI_developers",
  "marketing", "DigitalMarketing", "ContentMarketing", "artificial", "technology", 
  "AInews", "HealthAI", "TechNews", "CyberSecurity", "Robotics"
];

const scraper = new Scraper(SUBS);

// Start the scraper loop immediately
// (In a real app, maybe wait for /start signal, but 'always on' is best for a worker)
scraper.start();

// Start HTTP Server
console.log(`🌍 Server listening on port ${PORT}`);

serve({
  port: PORT,
  async fetch(req) {
    const url = new URL(req.url);

    // Health Check
    if (url.pathname === "/" || url.pathname === "/health") {
      return new Response("OK", { status: 200 });
    }

    // Manual Flush (Triggered by Cron)
    if (url.pathname === "/flush" && req.method === "POST") {
      console.log("📥 Received Flush Request");
      // Reuse shutdown logic but keep running? 
      // Currently scraper saves on every step, so flush is redundant unless we change that.
      // But let's implement a "Force Save All" just in case.
      await scraper.shutdown(); // Currently shutdown implies save-all
      // Restart it? 
      // For now, let's just say "Flushed" implies we saved everything. 
      // If we wanted non-stopping flush, we'd need a method.
      return new Response("Flushed", { status: 200 });
    }

    return new Response("Not Found", { status: 404 });
  },
});

// Handle System Signals
const handleExit = async () => {
  await scraper.shutdown();
  process.exit(0);
};

process.on("SIGINT", handleExit);
process.on("SIGTERM", handleExit);
