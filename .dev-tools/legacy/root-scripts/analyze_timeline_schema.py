TOOL_METADATA = {
    "name": "Timeline Schema Analyzer",
    "description": "Maps the nested skeleton of a massive JSON file without loading all the data.",
    "usage": "Pass the path to the JSON file in the Args box (e.g., ../_samples/Timeline.json)."
}

import sys
import json
from pathlib import Path

def extract_schema(obj):
    """Recursively extracts the skeleton/schema of a JSON object."""
    if isinstance(obj, dict):
        schema = {}
        for k, v in obj.items():
            schema[k] = extract_schema(v)
        return schema
    elif isinstance(obj, list):
        if not obj:
            return ["empty list"]
        # Just look at the very first item to define the list's structure
        return [extract_schema(obj[0])]
    else:
        # Return the data type (str, int, float, etc.)
        return type(obj).__name__

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Error: Please provide the path to Timeline.json as an argument.")
        print("Example: ../_samples/Timeline.json")
        sys.exit(1)

    target_file = Path(sys.argv[1])

    if not target_file.exists():
        print(f"Error: Cannot find {target_file}.")
        print("Make sure the workspace name matches what you typed in the UI!")
        exit(1)
        
    print("Loading the 93MB JSON into memory... give it a few seconds...")
    with open(target_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print("Mapping the JSON structure...")
    schema = extract_schema(data)
    
    out_path = Path("../timeline_schema_dump.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2)
        
    print(f"\nSuccess! The skeleton has been saved to: {out_path.resolve()}")
