# Reddit Scraper V3: Architectural Pseudocode

## 1. Initialization (Startup)
PROGRAM Main:
    INITIALIZE RateController (PID Loop for API limits)
    INITIALIZE PriorityAllocator (Resource distribution logic)
    INITIALIZE DiscoveryPoller (Finds new/hot posts)
    INITIALIZE StorageDriver (Local Disk or S3)
    
    LOAD Subreddit_Priorities from "subreddit_priorities.txt"
    
    START MainLoop()

## 2. The Main Loop (Runs Forever)
FUNCTION MainLoop:
    WHILE True:
        # A. Discovery Phase
        IF TimeToPoll():
            NewPosts = DiscoveryPoller.Poll(Subreddits)
            FOR EACH Post in NewPosts:
                RegisterPost(Post.ID) # Add to tracking system
        
        # B. Scheduling Phase
        UpdateCoverageFractions() # Decide % of resources per subreddit
        UpdateTemperatures()      # Calc "Hotness" of every tracked post
        
        Queue = ScheduleNext(ActivePosts, RateController.Gain)
        Batch = GetNextBatch(Queue, BatchSize)
        
        # C. Execution Phase (The "Work")
        FOR EACH PostID in Batch:
            TRY:
                ThreadData = RedditAPI.Fetch(PostID)
                
                # DAG Merge (The "Diff" Engine)
                Graph = LoadOrNewDAG(PostID)
                Stats = Graph.Merge(ThreadData) # Updates score/text history
                
                # Save & Log
                Storage.Save(Graph)
                Log(Stats) # e.g., "+5 comments, Score +10"
                
                # Feedback Loop
                RecordScrapeStats(PostID, Stats) # Feeds into Temperature
                
            CATCH Errors:
                Handle(403, 404, 429)
                
        # D. Rate Control (PID)
        Calculate MeasuredRPS()
        RateController.Update(MeasuredRPS) # Adjusts "Gain" (Speed)
        
        SLEEP(Small_Delay)

## 3. Key Algorithms

### A. Temperature (The "Interest" Metric)
FUNCTION ComputeTemperature(Post):
    # "How active is this post right now?"
    Activity = (NewComments + Abs(ScoreChange)) / TimeDelta
    
    # Exponential Moving Average
    Post.Rate = (Alpha * Activity) + ((1-Alpha) * Post.Rate)
    
    # The "Cooling" Factor
    Post.Temperature = Post.Rate * DecayFactor(Post.Age)
    
    # If Temperature drops near zero -> RETIRE Post

### B. Priority Allocator (The "Budgeter")
FUNCTION ComputeCoverage(Subreddit):
    # Ensure important subs get more API calls
    TotalCapacity = GlobalRateLimit * CurrentGain
    
    AllocatedSlots = TotalCapacity * Subreddit.PriorityWeight
    
    RETURN AllocatedSlots

### C. DAG Merge (The "Version Control")
FUNCTION DAG.Merge(IncomingNodes):
    FOR Node in IncomingNodes:
        IF Node exists in Graph:
            IF Score changed: Append to ScoreHistory[]
            IF Text changed:  Append to TextHistory[]
        ELSE:
            Add Node to Graph
            Mark as "New"
            
    CheckForDeletions(IncomingNodes vs Graph)