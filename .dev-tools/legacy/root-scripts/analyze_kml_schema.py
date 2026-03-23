TOOL_METADATA = {
    "name": "KML Schema Analyzer",
    "description": "Maps the nested skeleton of a KML or KMZ file and summarizes placemarks, geometries, tags, and paths.",
    "usage": "Pass the path to the KML or KMZ file in the Args box (e.g., ../_samples/customers.kml)."
}

import sys
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter, defaultdict


def strip_ns(tag: str) -> str:
    """Remove XML namespace from a tag name."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def load_kml_root(target_file: Path):
    """
    Load a KML root element from either:
    - .kml directly
    - .kmz by extracting the first .kml found inside
    """
    suffix = target_file.suffix.lower()

    if suffix == ".kml":
        tree = ET.parse(target_file)
        return tree.getroot(), str(target_file)

    if suffix == ".kmz":
        with zipfile.ZipFile(target_file, "r") as zf:
            kml_names = [name for name in zf.namelist() if name.lower().endswith(".kml")]
            if not kml_names:
                raise FileNotFoundError("No .kml file found inside the .kmz archive.")

            # Prefer doc.kml if present, otherwise first kml
            chosen = "doc.kml" if "doc.kml" in kml_names else kml_names[0]
            with zf.open(chosen) as f:
                tree = ET.parse(f)
                return tree.getroot(), f"{target_file}::{chosen}"

    raise ValueError("Unsupported file type. Please provide a .kml or .kmz file.")


def extract_element_signature(elem):
    """
    Build a structural summary of a single XML element:
    - tag
    - attributes
    - child tags
    - whether it has text
    """
    child_tags = [strip_ns(child.tag) for child in list(elem)]
    text = (elem.text or "").strip()

    return {
        "tag": strip_ns(elem.tag),
        "attributes": sorted(list(elem.attrib.keys())),
        "has_text": bool(text),
        "child_tags": sorted(list(set(child_tags))),
    }


def merge_signatures(base, new):
    """Merge two element signatures into one generalized signature."""
    if not base:
        return {
            "tag": new["tag"],
            "attributes": sorted(set(new["attributes"])),
            "has_text": new["has_text"],
            "child_tags": sorted(set(new["child_tags"])),
        }

    return {
        "tag": base["tag"],
        "attributes": sorted(set(base["attributes"]) | set(new["attributes"])),
        "has_text": base["has_text"] or new["has_text"],
        "child_tags": sorted(set(base["child_tags"]) | set(new["child_tags"])),
    }


def walk_schema(elem, path, schema_map, path_counter, tag_counter, depth=0, max_depth=50):
    """Recursively walk the XML tree and collect schema information."""
    if depth > max_depth:
        return

    tag_name = strip_ns(elem.tag)
    current_path = f"{path}/{tag_name}" if path else f"/{tag_name}"

    path_counter[current_path] += 1
    tag_counter[tag_name] += 1

    signature = extract_element_signature(elem)
    schema_map[current_path] = merge_signatures(schema_map.get(current_path), signature)

    for child in list(elem):
        walk_schema(child, current_path, schema_map, path_counter, tag_counter, depth + 1, max_depth)


def find_first_text(elem, child_tag_name):
    """Find the text of the first matching direct child tag."""
    for child in list(elem):
        if strip_ns(child.tag) == child_tag_name:
            return (child.text or "").strip()
    return ""


def detect_geometry_type(placemark):
    """Return the first geometry tag found under a Placemark."""
    geometry_tags = {
        "Point", "LineString", "Polygon",
        "MultiGeometry", "LinearRing", "Model",
        "gx:Track", "Track"
    }

    stack = [placemark]
    while stack:
        node = stack.pop()
        tag_name = strip_ns(node.tag)
        if tag_name in geometry_tags:
            return tag_name
        stack.extend(list(node))
    return "Unknown"


def summarize_placemarks(root):
    """Collect sample placemark info: name, geometry type, and whether coordinates exist."""
    placemarks = []
    for elem in root.iter():
        if strip_ns(elem.tag) == "Placemark":
            name = find_first_text(elem, "name")
            geometry = detect_geometry_type(elem)

            has_coordinates = False
            for sub in elem.iter():
                if strip_ns(sub.tag) == "coordinates":
                    coord_text = (sub.text or "").strip()
                    if coord_text:
                        has_coordinates = True
                        break

            placemarks.append({
                "name": name,
                "geometry_type": geometry,
                "has_coordinates": has_coordinates,
            })
    return placemarks


def build_tree_skeleton(elem):
    """
    Build a simplified nested tag skeleton from the first occurrence path.
    This is closer in spirit to your JSON schema extractor.
    """
    children = list(elem)
    if not children:
        text = (elem.text or "").strip()
        return {
            "tag": strip_ns(elem.tag),
            "type": "text" if text else "empty"
        }

    grouped = defaultdict(list)
    for child in children:
        grouped[strip_ns(child.tag)].append(child)

    child_schema = {}
    for tag_name, nodes in grouped.items():
        first = nodes[0]
        schema = build_tree_skeleton(first)
        if len(nodes) > 1:
            child_schema[tag_name] = [schema]
        else:
            child_schema[tag_name] = schema

    return {
        "tag": strip_ns(elem.tag),
        "attributes": sorted(list(elem.attrib.keys())),
        "children": child_schema
    }


def main():
    if len(sys.argv) < 2:
        print("Error: Please provide the path to a .kml or .kmz file as an argument.")
        print("Example: ../_samples/customers.kml")
        sys.exit(1)

    target_file = Path(sys.argv[1])

    if not target_file.exists():
        print(f"Error: Cannot find {target_file}.")
        sys.exit(1)

    print(f"Loading KML/KMZ from: {target_file}")
    root, source_used = load_kml_root(target_file)

    print("Mapping XML structure...")
    schema_map = {}
    path_counter = Counter()
    tag_counter = Counter()

    walk_schema(root, "", schema_map, path_counter, tag_counter)

    placemarks = summarize_placemarks(root)
    geometry_counter = Counter(p["geometry_type"] for p in placemarks)

    out = {
        "source": source_used,
        "root_tag": strip_ns(root.tag),
        "tag_counts": dict(tag_counter.most_common()),
        "path_counts": dict(path_counter.most_common()),
        "schema_by_path": schema_map,
        "tree_skeleton": build_tree_skeleton(root),
        "placemark_summary": {
            "count": len(placemarks),
            "geometry_counts": dict(geometry_counter),
            "sample_placemarks": placemarks[:25]
        }
    }

    out_path = Path("../kml_schema_dump.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"\nSuccess! The KML skeleton has been saved to: {out_path.resolve()}")
    print(f"Placemark count: {len(placemarks)}")
    print(f"Geometry types: {dict(geometry_counter)}")


if __name__ == "__main__":
    main()
