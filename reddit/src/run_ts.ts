import { Scraper } from "./scraper";

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

async function main() {
  const scraper = new Scraper(SUBS);
  
  // Add a known seed thread to start immediately
  scraper.addThread("1p1kpmu"); 

  // Handle Graceful Shutdown
  const handleExit = () => {
      scraper.shutdown();
      process.exit(0);
  };

  process.on("SIGINT", handleExit);
  process.on("SIGTERM", handleExit);

  await scraper.start();
}

main();
