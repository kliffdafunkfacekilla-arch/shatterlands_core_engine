import sqlite3
import json
import os

def apply_override(q, r, modifier_dict=None, append_tags=None, db_path=None):
    if db_path is None:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "world_state.db")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT micro_data_json FROM global_hexes WHERE q=? AND r=?", (q, r))
    row = cursor.fetchone()

    if row:
        micro_data = {}
        if row[0]:
            try:
                parsed_json = json.loads(row[0])
                if isinstance(parsed_json, list):
                    micro_data = {"hexes": parsed_json}
                elif isinstance(parsed_json, dict):
                    micro_data = parsed_json
            except json.JSONDecodeError:
                pass

        if "rule_overrides" not in micro_data:
            micro_data["rule_overrides"] = {}
        if "tags" not in micro_data:
            micro_data["tags"] = []

        if modifier_dict:
            for key, value in modifier_dict.items():
                micro_data["rule_overrides"][key] = value

        if append_tags:
            for tag in append_tags:
                if tag not in micro_data["tags"]:
                    micro_data["tags"].append(tag)

        updated_json = json.dumps(micro_data)
        cursor.execute("UPDATE global_hexes SET micro_data_json=? WHERE q=? AND r=?", (updated_json, q, r))
        conn.commit()

    conn.close()

if __name__ == "__main__":
    pass
