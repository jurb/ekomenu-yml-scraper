#!/usr/bin/env -S uv run --script
"""
Combine individual YAML recipe files into one combined YAML file.
Takes individual recipe YAML files and outputs them in the same format
as ekomenu2yml.py when multiple URLs are provided.
"""

import argparse
import sys
from pathlib import Path
import yaml
import re

def load_recipe_yaml(yaml_path):
    """Load a single recipe YAML file and return the recipe data."""
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data
    except Exception as e:
        print(f"Error loading {yaml_path}: {e}", file=sys.stderr)
        return None

def render_recipe_fields(d: dict, lines: list, indent: str):
    """Render recipe fields with proper indentation (copied from ekomenu2yml.py)."""
    def push(k, v):
        if v in (None, "", []): return
        if isinstance(v, str) and ("\n" in v or k in {"notes", "ingredients", "directions", "nutritional_info", "photo"}):
            lines.append(f"{indent}{k}: |")
            lines.extend(f"{indent}  {ln}" for ln in v.split("\n"))
        else:
            lines.append(f"{indent}{k}: {v}")
    push("servings", d.get("servings"))
    push("cook_time", d.get("cook_time"))
    push("source", d.get("source"))
    push("source_url", d.get("source_url"))
    push("photo", d.get("photo"))
    push("nutritional_info", d.get("nutritional_info"))
    push("notes", d.get("notes"))
    push("ingredients", d.get("ingredients"))
    push("directions", d.get("directions"))

def render_combined_yaml(recipes):
    """Render multiple recipes in combined YAML format (copied from ekomenu2yml.py)."""
    lines = []
    for i, d in enumerate(recipes):
        if i > 0:
            lines.append("")
        lines.append("- name: " + (d.get("name") or ""))
        render_recipe_fields(d, lines, "  ")
    return "\n".join(lines) + "\n"

def main():
    parser = argparse.ArgumentParser(description="Combine individual YAML recipe files into one combined file")
    parser.add_argument("yaml_files", nargs="+", help="YAML recipe files to combine")
    parser.add_argument("--output", "-o", default="combined_recipes.yml", 
                       help="Output file for combined recipes (default: combined_recipes.yml)")
    parser.add_argument("--sort-by-rating", action="store_true", 
                       help="Sort recipes by rating (highest first)")
    
    args = parser.parse_args()
    
    # Load all recipe files
    recipes = []
    for yaml_file in args.yaml_files:
        yaml_path = Path(yaml_file)
        if not yaml_path.exists():
            print(f"File not found: {yaml_file}", file=sys.stderr)
            continue
            
        recipe_data = load_recipe_yaml(yaml_path)
        if recipe_data:
            recipes.append(recipe_data)
            print(f"Loaded: {yaml_path.name}")
    
    if not recipes:
        print("No recipes loaded", file=sys.stderr)
        sys.exit(1)
    
    # Sort by rating if requested
    if args.sort_by_rating:
        def extract_rating(recipe):
            """Extract rating from recipe notes."""
            notes = recipe.get("notes", "")
            if notes:
                match = re.search(r'Beoordeling: ([\d.,]+)', notes)
                if match:
                    try:
                        return float(match.group(1).replace(',', '.'))
                    except ValueError:
                        return 0.0
            return 0.0
        
        recipes.sort(key=extract_rating, reverse=True)
        print(f"Sorted {len(recipes)} recipes by rating (highest first)")
    
    # Generate combined YAML
    combined_yaml = render_combined_yaml(recipes)
    
    # Write output
    output_path = Path(args.output)
    output_path.write_text(combined_yaml, encoding='utf-8')
    
    print(f"Combined {len(recipes)} recipes into: {output_path}")

if __name__ == "__main__":
    main()