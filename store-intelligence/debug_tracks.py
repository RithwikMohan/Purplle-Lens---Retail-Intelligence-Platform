import json
from collections import defaultdict

events = [json.loads(l) for l in open('pipeline/events_store1.jsonl') if l.strip()]

tracks = defaultdict(lambda: {'frames': 0, 'is_staff': False, 'types': set()})
for e in events:
    vid = e.get('visitor_id', '')
    tracks[vid]['is_staff'] = e.get('is_staff', False)
    tracks[vid]['types'].add(e.get('event_type', ''))
    tracks[vid]['frames'] += 1

customers = {k: v for k, v in tracks.items() if not v['is_staff']}
staff = {k: v for k, v in tracks.items() if v['is_staff']}

print(f"Total customer tracks: {len(customers)}")
for vid, info in sorted(customers.items()):
    print(f"  {vid}: events={info['frames']}, types={sorted(info['types'])}")

print(f"\nTotal staff tracks: {len(staff)}")
for vid, info in sorted(staff.items()):
    print(f"  {vid}: events={info['frames']}, types={sorted(info['types'])}")
