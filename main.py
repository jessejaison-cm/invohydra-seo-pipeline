# main.py
"""
Main execution script for the InvoHydra SEO Pipeline.
Runs the active agents sequentially to process keywords and output structured SEO clusters,
and then generates blog posts for the clusters.
"""

import json
from agents.planner import load_keywords, load_feature_truth, cluster_keywords
from agents.writer import generate_all_blogs

def main():
    print("🚀 Starting InvoHydra SEO Pipeline...")
    
    # Paths to source data files
    keywords_path = "data/manual_keywords.json"
    features_path = "data/feature_truth.json"
    output_path = "data/clustered_keywords.json"
    blogs_dir = "data/blogs"
    
    print(f"📦 Loading manual keywords from: {keywords_path}")
    keywords = load_keywords(keywords_path)
    print(f"✅ Loaded {len(keywords)} keywords.")
    
    print(f"📦 Loading feature capabilities map from: {features_path}")
    features = load_feature_truth(features_path)
    
    print("🧠 Invoking Agent 3 (Semantic Intent Clusterer)...")
    results = cluster_keywords(keywords, features)
    
    print(f"💾 Saving clustered and filtered keywords to: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print("✍️ Invoking Agent 4 (Blog Writer)...")
    generate_all_blogs(output_path, blogs_dir)
        
    print("🎉 Pipeline run complete! Check data/clustered_keywords.json and data/blogs/ for results.")

if __name__ == "__main__":
    main()
