import { RedditAPI } from "./api";
import { DAG } from "./dag";

async function main() {
  const postId = "1p1kpmu"; // The NVIDIA thread we saw earlier
  const api = new RedditAPI();
  
  console.log(`--- STEP 1: Fetching ${postId} ---`);
  const nodes = await api.fetchThread(postId);
  console.log(`Fetched ${nodes.length} nodes.`);
  
  console.log(`--- STEP 2: Merging into DAG ---`);
  const dag = new DAG(); // Empty start
  dag.merge(nodes, new Date().toISOString());
  
  const map = dag.getNodes();
  console.log(`DAG Size: ${map.size}`);
  
  // Inspect the root
  const root = map.get(postId);
  if (root) {
    console.log("Root Node:", {
      title: root.title,
      author: root.author,
      score: root.scoreHistory[0].value
    });
  } else {
    console.error("Root node not found!");
  }
  
  // Inspect a comment
  const firstComment = Array.from(map.values()).find(n => n.parentId === postId);
  if (firstComment) {
    console.log("First Reply:", {
        id: firstComment.id,
        body: firstComment.textHistory[0].value.substring(0, 50) + "..."
    });
  }
}

main().catch(console.error);
