import json
from eraseproof.events import Event

print(json.dumps(Event.model_json_schema(), indent=2))
